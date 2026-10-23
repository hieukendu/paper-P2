"""Pinned, locally loaded Nomic text encoder adapter.

The Nomic snapshots refer to external model code through ``auto_map``.  This
adapter loads only the reviewed code revision from a local snapshot and never
enables Transformers' general ``trust_remote_code`` path.
"""

from __future__ import annotations

import gc
import hashlib
import importlib.util
from pathlib import Path
import sys
import time
import types

import numpy as np
from safetensors import safe_open

from .io import read_json

CODE_REPO_ID = "nomic-ai/nomic-bert-2048"
CODE_REVISION = "7710840340a098cfb869c4f65e87cf2b1b70caca"
CODE_FILES = {
    "configuration_hf_nomic_bert.py":
        "f7871694b8de3d3df4ac6640313d5799ce323261a0fb90c5cc567ecc34a0039e",
    "modeling_hf_nomic_bert.py":
        "3b24a366c4cc31b869466ccfb7bbb8879e138c97f8de06c83d4fa1e31a21f149",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_code_snapshot(snapshot, revision=CODE_REVISION, expected=None):
    """Verify the exact reviewed Python files before importing them."""
    if revision != CODE_REVISION:
        raise ValueError("Nomic adapter code revision is not the reviewed pin")
    root = Path(snapshot)
    expected = CODE_FILES if expected is None else expected
    if expected != CODE_FILES:
        raise ValueError("Nomic adapter code manifest differs from the reviewed pin")
    actual = {}
    for relative, checksum in CODE_FILES.items():
        path = root / relative
        if not path.is_file() or _sha256(path) != checksum:
            raise ValueError(f"Nomic adapter code checksum mismatch: {relative}")
        actual[relative] = checksum
    return actual


def _load_reviewed_modules(snapshot, revision, code_files):
    root = Path(snapshot)
    verify_code_snapshot(root, revision, code_files)
    package_name = f"_mixindex_nomic_{hashlib.sha256(str(root).encode()).hexdigest()[:16]}"
    package = sys.modules.get(package_name)
    if package is None:
        package = types.ModuleType(package_name)
        package.__path__ = [str(root)]
        sys.modules[package_name] = package
    loaded = {}
    for module in ("configuration_hf_nomic_bert", "modeling_hf_nomic_bert"):
        full_name = f"{package_name}.{module}"
        existing = sys.modules.get(full_name)
        if existing is None:
            path = root / f"{module}.py"
            spec = importlib.util.spec_from_file_location(full_name, path)
            if spec is None or spec.loader is None:
                raise ImportError(f"Cannot load pinned Nomic module: {module}")
            existing = importlib.util.module_from_spec(spec)
            sys.modules[full_name] = existing
            spec.loader.exec_module(existing)
        loaded[module] = existing
    return loaded["configuration_hf_nomic_bert"], loaded["modeling_hf_nomic_bert"]


def pool_nomic(last_hidden_state, attention_mask, layer_norm=False):
    """Apply the published masked mean, optional layer norm, and L2 norm."""
    import torch
    mask = attention_mask.unsqueeze(-1).to(dtype=last_hidden_state.dtype)
    pooled = (last_hidden_state * mask).sum(dim=1) / mask.sum(dim=1).clamp_min(1e-9)
    if layer_norm:
        pooled = torch.nn.functional.layer_norm(pooled, (pooled.shape[-1],))
    return torch.nn.functional.normalize(pooled, p=2, dim=1)


class NomicEncoderAdapter:
    """Sentence-transformer-compatible Nomic v1/v1.5 adapter."""

    def __init__(self, spec, device="cuda", batch_size=8):
        import torch
        from transformers import AutoTokenizer

        if spec.get("adapter") != "nomic_pinned":
            raise ValueError("NomicEncoderAdapter requires the pinned adapter recipe")
        if spec.get("code_repo_id") != CODE_REPO_ID:
            raise ValueError("Nomic adapter code repository is not the reviewed pin")
        code_files = verify_code_snapshot(spec["code_snapshot"], spec["code_revision"],
                                          spec.get("code_files", CODE_FILES))
        configuration, modeling = _load_reviewed_modules(
            spec["code_snapshot"], spec["code_revision"], code_files)
        model_dir = Path(spec["snapshot"])
        weights = model_dir / "model.safetensors"
        if not weights.is_file() or (model_dir / "pytorch_model.bin").exists():
            raise ValueError("Nomic adapter requires the reviewed safetensors-only snapshot")
        raw_config = read_json(model_dir / "config.json")
        config = configuration.NomicBertConfig.from_pretrained(
            str(model_dir), local_files_only=True)
        if config.hidden_size != spec["dim"] or config.n_embd != spec["dim"]:
            raise ValueError("Nomic checkpoint dimension differs from the model registry")
        raw_positions = int(raw_config.get("n_positions", 0))
        if config.rotary_emb_fraction <= 0 and int(raw_config.get("max_position_embeddings", 0)) < spec["max_tokens"]:
            raise ValueError("Nomic checkpoint position limit is below the pinned recipe")
        if config.rotary_emb_fraction > 0 and raw_positions < spec["max_tokens"]:
            raise ValueError("Nomic rotary checkpoint position limit is below the pinned recipe")
        # Transformers 4.51 normalizes GPT2Config.n_positions from the legacy
        # max_position_embeddings field (2048 in v1.5), while the pinned Nomic
        # JSON explicitly declares the rotary 8192 context.  Rotary models do
        # not allocate learned position embeddings, so restore the JSON value.
        if config.rotary_emb_fraction > 0:
            config.n_positions = max(config.n_positions, raw_positions, spec["max_tokens"])

        # Check the safetensors key/shape contract before the external module
        # receives any weights.  The model code's local path then uses the
        # safetensors loader; it never needs pickle deserialization.
        with safe_open(str(weights), framework="pt", device="cpu") as handle:
            weight_keys = set(handle.keys())
            weight_shapes = {key: tuple(handle.get_slice(key).get_shape()) for key in weight_keys}
        probe = modeling.NomicBertModel(config, add_pooling_layer=False)
        model_keys = set(probe.state_dict())
        if weight_keys != model_keys:
            missing = sorted(model_keys - weight_keys)[:3]
            extra = sorted(weight_keys - model_keys)[:3]
            raise ValueError(f"Nomic safetensors keys differ (missing={missing}, extra={extra})")
        if any(tuple(probe.state_dict()[key].shape) != weight_shapes[key] for key in model_keys):
            raise ValueError("Nomic safetensors shape differs from the pinned model")
        del probe

        self.spec = {**spec, "code_files": code_files}
        self.batch_size = batch_size
        self.device = device
        self.torch = torch
        self.tokenizer = AutoTokenizer.from_pretrained(str(model_dir), local_files_only=True)
        self.tokenizer.model_max_length = spec["max_tokens"]
        self.model = modeling.NomicBertModel.from_pretrained(
            str(model_dir), config=config, torch_dtype=torch.float32, strict=True)
        self.model.to(device).float().eval()
        self.model.requires_grad_(False)
        self.layer_norm = spec["pooling"] == "masked_mean_layernorm"
        self.cost = {"calls": 0, "documents": 0, "nonpad_tokens": 0,
                     "padded_tokens": 0, "truncated_documents": 0, "wall_seconds": 0.0}

    def _encode(self, texts, prefix):
        if not texts:
            return np.empty((0, self.spec["dim"]), dtype=np.float32)
        prepared = [prefix + text for text in texts]
        raw = self.tokenizer(prepared, padding=False, truncation=False,
                             add_special_tokens=True, verbose=False)["input_ids"]
        lengths = np.asarray([len(ids) for ids in raw], dtype=np.int64)
        effective = np.minimum(lengths, self.spec["max_tokens"])
        self.last_lengths = {"raw": lengths, "effective": effective}
        order = np.argsort(-effective, kind="stable")
        output = np.empty((len(texts), self.spec["dim"]), dtype=np.float32)
        if self.device.startswith("cuda"):
            self.torch.cuda.synchronize()
        started = time.monotonic()
        try:
            with self.torch.inference_mode():
                for start in range(0, len(order), self.batch_size):
                    indices = order[start:start + self.batch_size]
                    batch = self.tokenizer(
                        [prepared[int(index)] for index in indices],
                        padding=True, truncation=True, max_length=self.spec["max_tokens"],
                        return_tensors="pt", verbose=False,
                    )
                    batch = {key: value.to(self.device) for key, value in batch.items()
                             if hasattr(value, "to")}
                    self.cost["calls"] += 1
                    self.cost["documents"] += len(indices)
                    self.cost["nonpad_tokens"] += int(batch["attention_mask"].sum().item())
                    self.cost["padded_tokens"] += int(batch["attention_mask"].shape[0] *
                                                       batch["attention_mask"].shape[1])
                    self.cost["truncated_documents"] += int(
                        sum(lengths[int(index)] > self.spec["max_tokens"] for index in indices))
                    values = self.model(**batch).last_hidden_state
                    values = pool_nomic(values, batch["attention_mask"], self.layer_norm)
                    output[indices] = values.detach().float().cpu().numpy()
            norms = np.linalg.norm(output, axis=1)
            if not np.isfinite(output).all() or not np.allclose(norms, 1, atol=1e-4, rtol=0):
                raise ValueError("Nomic adapter produced invalid vectors")
            return output
        finally:
            if self.device.startswith("cuda"):
                self.torch.cuda.synchronize()
            self.cost["wall_seconds"] += time.monotonic() - started

    def encode_documents(self, texts, *, token_budget=None):
        if token_budget is not None:
            raise ValueError("Nomic adapter does not support token-budget batching")
        return self._encode(texts, self.spec["document_prefix"])

    def encode_queries(self, texts):
        return self._encode(texts, self.spec["query_prefix"])

    def close(self):
        self.model.to("cpu")
        del self.model
        gc.collect()
        if self.device.startswith("cuda"):
            self.torch.cuda.empty_cache()
