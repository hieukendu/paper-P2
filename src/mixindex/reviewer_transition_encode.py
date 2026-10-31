"""Encode FiQA once for the REV-07 transition pairs with pinned adapters."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from .config import load_config
from .encoders import model_specs
from .io import file_digest, read_json
from .nomic_adapter import NomicEncoderAdapter


def _read_jsonl(path: Path, text_key: str = "text"):
    ids, texts = [], []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            ids.append(str(row["id"]))
            texts.append(str(row.get(text_key, row.get("query", ""))))
    return ids, texts


def _record_for(spec: dict, root: Path) -> dict:
    lock = root / "cache/models/models.lock.json"
    entries = read_json(lock)
    key = __import__("hashlib").sha256(json.dumps(spec, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if key not in entries:
        raise ValueError(f"model is not resolved/pinned: {spec['repo_id']}")
    return entries[key]


def _encode_standard(record: dict, texts: list[str], prefix: str, max_tokens: int, batch_size: int) -> np.ndarray:
    import torch
    from transformers import AutoModel, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(record["snapshot"], local_files_only=True)
    model = AutoModel.from_pretrained(record["snapshot"], local_files_only=True).cuda().eval().float()
    outputs = []
    with torch.inference_mode():
        for start in range(0, len(texts), batch_size):
            batch = [prefix + value for value in texts[start : start + batch_size]]
            encoded = tokenizer(batch, padding=True, truncation=True, max_length=max_tokens, return_tensors="pt")
            encoded = {key: value.cuda(non_blocking=True) for key, value in encoded.items()}
            hidden = model(**encoded).last_hidden_state
            pooled = hidden[:, 0, :]
            outputs.append(torch.nn.functional.normalize(pooled, p=2, dim=1).float().cpu().numpy())
            if start == 0 or (start + len(batch)) % max(batch_size * 256, 1024) == 0:
                print(f"{record['repo_id']} {start + len(batch)}/{len(texts)}", flush=True)
    if torch.cuda.is_available():
        torch.cuda.synchronize()
    model.to("cpu")
    del model, tokenizer
    torch.cuda.empty_cache()
    return np.concatenate(outputs, axis=0).astype(np.float32, copy=False)


def _encode_nomic(record: dict, texts: list[str], prefix: str, batch_size: int) -> np.ndarray:
    adapter = NomicEncoderAdapter(record, device="cuda", batch_size=batch_size)
    outputs = []
    for start in range(0, len(texts), 1024):
        values = adapter._encode(texts[start : start + 1024], prefix)
        outputs.append(values)
        print(f"{record['repo_id']} {start + len(values)}/{len(texts)}", flush=True)
    adapter.close()
    return np.concatenate(outputs, axis=0).astype(np.float32, copy=False)


def encode_pair(root: Path, pair: str, role: str, output: Path, batch_size: int = 8) -> dict:
    root = Path(root)
    cfg = load_config(Path("configs/base.yaml"), root=root)
    specs = model_specs(pair, root)
    record = _record_for(specs[role], root)
    docs_path = root / "runs/reviewer_inputs/fiqa_text/documents.jsonl"
    queries_path = root / "runs/reviewer_inputs/fiqa_text/queries.jsonl"
    doc_ids, doc_texts = _read_jsonl(docs_path)
    query_ids, query_texts = _read_jsonl(queries_path)
    started = time.monotonic()
    if record.get("adapter") == "nomic_pinned":
        doc_vectors = _encode_nomic(record, doc_texts, specs[role]["document_prefix"], batch_size)
        query_vectors = _encode_nomic(record, query_texts, specs[role]["query_prefix"], batch_size)
    else:
        doc_vectors = _encode_standard(record, doc_texts, specs[role]["document_prefix"], specs[role]["max_tokens"], batch_size)
        query_vectors = _encode_standard(record, query_texts, specs[role]["query_prefix"], specs[role]["max_tokens"], batch_size)
    if doc_vectors.shape[0] != len(doc_ids) or query_vectors.shape[0] != len(query_ids):
        raise ValueError("encoder row alignment changed")
    output.mkdir(parents=True, exist_ok=True)
    doc_path = output / f"{pair}-{role}-documents.npy"
    query_path = output / f"{pair}-{role}-queries.npy"
    np.save(doc_path, doc_vectors)
    np.save(query_path, query_vectors)
    meta = {
        "pair": pair,
        "role": role,
        "repo_id": record["repo_id"],
        "resolved_revision": record["resolved_revision"],
        "snapshot": record["snapshot"],
        "adapter": record.get("adapter"),
        "dim": int(doc_vectors.shape[1]),
        "documents": len(doc_ids),
        "queries": len(query_ids),
        "document_prefix": specs[role]["document_prefix"],
        "query_prefix": specs[role]["query_prefix"],
        "max_tokens": specs[role]["max_tokens"],
        "batch_size": batch_size,
        "documents_sha256": file_digest(doc_path),
        "queries_sha256": file_digest(query_path),
        "document_ids_sha256": __import__("hashlib").sha256("\n".join(doc_ids).encode()).hexdigest(),
        "query_ids_sha256": __import__("hashlib").sha256("\n".join(query_ids).encode()).hexdigest(),
        "elapsed_seconds": time.monotonic() - started,
    }
    (output / f"{pair}-{role}.json").write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(meta, sort_keys=True))
    return meta


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--pair", choices=("nomic", "bge"), required=True)
    parser.add_argument("--role", choices=("old", "new"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=8)
    args = parser.parse_args()
    encode_pair(args.root, args.pair, args.role, args.output, args.batch_size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
