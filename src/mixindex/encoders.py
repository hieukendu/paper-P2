"""Revision-pinned, frozen encoder adapters with explicit prompt semantics."""

import gc
from pathlib import Path
import time

from huggingface_hub import HfApi, snapshot_download
import numpy as np
import yaml

from .config import load_runtime_env, project_root
from .io import digest, file_lock, read_json, write_json


def model_specs(pair, root=None):
    registry = yaml.safe_load((project_root(root) / "configs/models.yaml").read_text())
    if pair not in registry:
        raise ValueError(f"Unknown model pair {pair}")
    return registry[pair]


def resolve_model(spec, paths, root):
    load_runtime_env(root)
    model_root = Path(paths["cache"]) / "models"
    lock_path = model_root / "models.lock.json"
    with file_lock(model_root / ".models.lock"):
        registry = read_json(lock_path) if lock_path.exists() else {}
        key = digest(spec)
        if key in registry:
            record = registry[key]
            snapshot = snapshot_download(record["repo_id"], revision=record["resolved_revision"],
                              cache_dir=str(model_root / "hub"), local_files_only=True,
                              allow_patterns=record["download_patterns"])
            if record.get("format_conversion"):
                from .model_formats import convert_reviewed_checkpoint
                converted, conversion = convert_reviewed_checkpoint(snapshot, model_root,
                    record["repo_id"], record["resolved_revision"],
                    record["format_conversion"]["recipe"]["source_sha256"])
                if str(converted) != record["snapshot"] or conversion != record["format_conversion"]:
                    raise ValueError("Converted model lock differs from verified conversion")
            if record.get("adapter") == "nomic_pinned":
                from .nomic_adapter import verify_code_snapshot
                verify_code_snapshot(record["code_snapshot"], record["code_revision"],
                                     record.get("code_files"))
            return record
        if spec.get("adapter") == "nomic_pinned":
            from .nomic_adapter import CODE_FILES, CODE_REPO_ID, CODE_REVISION, verify_code_snapshot
            if spec.get("code_repo_id") != CODE_REPO_ID or spec.get("code_revision") != CODE_REVISION:
                raise ValueError("Nomic model requires the reviewed external code pin")
            api = HfApi()
            info = api.model_info(spec["repo_id"], files_metadata=True)
            patterns = ["*.json", "*.safetensors", "*.txt", "*.model", "*.md"]
            snapshot = snapshot_download(spec["repo_id"], revision=info.sha,
                                         cache_dir=str(model_root / "hub"),
                                         allow_patterns=patterns, ignore_patterns=["*.bin", "*.h5"])
            code_info = api.model_info(CODE_REPO_ID, revision=CODE_REVISION, files_metadata=True)
            if code_info.sha != CODE_REVISION:
                raise ValueError("Pinned Nomic external code revision is unavailable")
            code_snapshot = snapshot_download(
                CODE_REPO_ID, revision=CODE_REVISION, cache_dir=str(model_root / "hub"),
                allow_patterns=[*CODE_FILES, "config.json", "README.md"],
                ignore_patterns=["*.bin", "*.safetensors"], max_workers=2)
            code_files = verify_code_snapshot(code_snapshot, CODE_REVISION, CODE_FILES)
            record = {**spec, "resolved_revision": info.sha, "snapshot": str(snapshot),
                      "download_patterns": patterns, "dtype": "float32", "trust_remote_code": False,
                      "code_snapshot": str(code_snapshot), "code_files": code_files}
            registry[key] = record
            write_json(lock_path, registry)
            return record
        api = HfApi()
        info = api.model_info(spec["repo_id"], files_metadata=True)
        patterns = ["*.json", "*.safetensors", "*.txt", "*.model", "*.md"]
        path = snapshot_download(spec["repo_id"], revision=info.sha,
                                 cache_dir=str(model_root / "hub"),
                                 allow_patterns=patterns,
                                 ignore_patterns=["onnx/*", "openvino/*", "*.bin", "*.h5", "*.msgpack"],
                                 max_workers=2)
        conversion = None
        if not list(Path(path).rglob("*.safetensors")):
            # Reviewed upstream BGE-M3 uses a standard XLM-R tensor-only state dict.
            if spec["repo_id"] != "BAAI/bge-m3":
                raise RuntimeError("Checkpoint has no safetensors; inspect format before enabling pickle")
            from huggingface_hub import hf_hub_download
            from .model_formats import convert_reviewed_checkpoint
            entry = next((f for f in info.siblings if f.rfilename == "pytorch_model.bin"), None)
            lfs = getattr(entry, "lfs", None)
            checksum = getattr(lfs, "sha256", None) or (lfs.get("sha256") if isinstance(lfs, dict) else None)
            if not checksum:
                raise ValueError("Upstream checkpoint requires a pinned LFS SHA256")
            hf_hub_download(spec["repo_id"], "pytorch_model.bin", revision=info.sha,
                            cache_dir=str(model_root / "hub"))
            path, conversion = convert_reviewed_checkpoint(path, model_root, spec["repo_id"], info.sha, checksum)
            patterns = [*patterns, "pytorch_model.bin"]
        record = {**spec, "resolved_revision": info.sha, "snapshot": path,
                  "dtype": "float32", "download_patterns": patterns, "trust_remote_code": False}
        record["snapshot"] = str(record["snapshot"])
        if conversion is not None:
            record["format_conversion"] = conversion
        registry[key] = record
        write_json(lock_path, registry)
        return record


class EncoderAdapter:
    def __init__(self, spec, device="cuda", batch_size=8):
        if spec["adapter"] != "sentence_transformer":
            raise NotImplementedError("Custom model code must be inspected and pinned before use")
        from sentence_transformers import SentenceTransformer
        import torch
        self.spec = spec
        self.batch_size = batch_size
        self.model = SentenceTransformer(spec["snapshot"], device=device, local_files_only=True,
                                         trust_remote_code=False)
        self.model.float().eval()
        self.model.requires_grad_(False)
        pooling = Path(spec["snapshot"]) / "1_Pooling/config.json"
        if pooling.exists():
            modes = read_json(pooling)
            expected = "pooling_mode_mean_tokens" if spec["pooling"] == "mean" else "pooling_mode_cls_token"
            if not modes.get(expected):
                raise ValueError("Snapshot pooling differs from the pinned adapter recipe")
        self.model.max_seq_length = spec["max_tokens"]
        self.model.default_prompt_name = None
        self.model.prompts = {}  # Prefixes below are applied exactly once for each role.
        if self.model.get_sentence_embedding_dimension() != spec["dim"]:
            raise ValueError("Checkpoint dimension differs from model registry")
        self.device = device
        self.torch = torch
        self.cost = {"calls": 0, "documents": 0, "nonpad_tokens": 0,
                     "padded_tokens": 0, "truncated_documents": 0, "wall_seconds": 0.0}

    def _encode(self, texts, prefix):
        if not texts:
            return np.empty((0, self.spec["dim"]), dtype=np.float32)
        prepared = [prefix + t for t in texts]
        tokenized = self.model.tokenizer(prepared, truncation=False, add_special_tokens=True,
                                          verbose=False)["input_ids"]
        lengths = np.array([min(len(ids), self.spec["max_tokens"]) for ids in tokenized])
        self.last_lengths = {"raw": np.array([len(ids) for ids in tokenized]), "effective": lengths}
        if self.device.startswith("cuda"):
            self.torch.cuda.synchronize()
        start = time.monotonic()
        # Bucket by actual token lengths and restore caller order. Each encode call is
        # one batch, so the padding count below describes batches actually executed.
        order = np.argsort(-lengths, kind="stable")
        output = np.empty((len(prepared), self.spec["dim"]), dtype=np.float32)
        try:
            with self.torch.inference_mode():
                for indices in (order[i:i + self.batch_size] for i in range(0, len(order), self.batch_size)):
                    # Charge attempted forwards too: OOM or validation failure is not free compute.
                    self.cost["calls"] += 1
                    self.cost["documents"] += len(indices)
                    self.cost["nonpad_tokens"] += int(lengths[indices].sum())
                    self.cost["padded_tokens"] += int(lengths[indices].max()) * len(indices)
                    self.cost["truncated_documents"] += sum(
                        len(tokenized[i]) > self.spec["max_tokens"] for i in indices)
                    values = self.model.encode([prepared[i] for i in indices], batch_size=len(indices),
                                                convert_to_numpy=True, normalize_embeddings=True,
                                                show_progress_bar=False)
                    output[indices] = values
            output = np.asarray(output, dtype=np.float32)
            validate_vectors(output, self.spec["dim"])
            return output
        finally:
            try:
                if self.device.startswith("cuda"):
                    self.torch.cuda.synchronize()
            finally:
                self.cost["wall_seconds"] += time.monotonic() - start

    def encode_documents(self, texts):
        return self._encode(texts, self.spec["document_prefix"])

    def encode_queries(self, texts):
        return self._encode(texts, self.spec["query_prefix"])

    def close(self):
        self.model.to("cpu")
        del self.model
        gc.collect()
        if self.device.startswith("cuda"):
            self.torch.cuda.empty_cache()


def build_encoder(spec, device="cuda", batch_size=8):
    if spec.get("adapter") == "nomic_pinned":
        from .nomic_adapter import NomicEncoderAdapter
        return NomicEncoderAdapter(spec, device, batch_size)
    return EncoderAdapter(spec, device, batch_size)


def validate_vectors(output, dimension=None):
    if output.ndim != 2 or (dimension is not None and output.shape[1] != dimension):
        raise ValueError("Invalid embedding shape")
    if not np.isfinite(output).all():
        raise ValueError("Nonfinite embedding")
    if len(output) and not np.allclose(np.linalg.norm(output, axis=1), 1, atol=1e-4, rtol=0):
        raise ValueError("Embedding is zero or not unit normalized")


def smoke_encoder(encoder, examples):
    documents = encoder.encode_documents(examples)
    queries = encoder.encode_queries(examples)
    repeat = encoder.encode_documents(examples)
    if not np.allclose(documents, repeat, atol=1e-5, rtol=1e-5):
        raise ValueError("Encoder repeat consistency failed")
    return {"status": "PASS", "dimension": documents.shape[1], "examples": len(examples),
            "query_shape": list(queries.shape), "cost": dict(encoder.cost),
            "device": encoder.device, "revision": encoder.spec["resolved_revision"]}
