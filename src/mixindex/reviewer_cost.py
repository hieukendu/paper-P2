"""REV-06 exclusive cost/storage benchmark on the frozen FiQA anchor.

The quality cells deliberately use cached target vectors.  This benchmark keeps
that mode separate from a measured live target-encoder probe, so a cached lookup
is never reported as zero encoder cost.  One warm-up is discarded; the three
measured migration repeats start from the same immutable FiQA pools and vectors.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import resource
import tempfile
import time

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from .config import load_config, redacted_config
from .data.prepare import validate_prepared
from .data.splits import sample_document_pools
from .index import ExactIndex
from .io import file_digest, write_json
from .maps import load_map_state, transform_global
from .migration import bootstrap_migration, emit_checkpoint, run_migration
from .vectors import PaidEmbeddingAccessor


def _load_jsonl(path: Path):
    ids, texts = [], []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            ids.append(str(row["id"]))
            texts.append(str(row.get("text", row.get("query", ""))))
    return ids, texts


def _peak_rss_bytes() -> int:
    # Linux reports KiB for ru_maxrss.
    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024)


def _recursive_bytes(path: Path) -> int:
    return int(sum(p.stat().st_size for p in path.rglob("*") if p.is_file())) if path.exists() else 0


def _stratified_rows(texts: list[str], count: int) -> np.ndarray:
    """Choose deterministic length-stratified rows for live encoder costing."""
    n = len(texts)
    count = min(int(count), n)
    if count == n:
        return np.arange(n, dtype=np.int64)
    lengths = np.asarray([len(text) for text in texts], dtype=np.int64)
    ordered = np.argsort(lengths, kind="stable")
    groups = np.array_split(ordered, min(32, count))
    selected = []
    for group in groups:
        if not len(group):
            continue
        take = max(1, int(round(count * len(group) / n)))
        positions = np.linspace(0, len(group) - 1, min(take, len(group)), dtype=np.int64)
        selected.extend(group[positions].tolist())
    selected = np.asarray(sorted(set(selected)), dtype=np.int64)
    if len(selected) > count:
        selected = selected[np.linspace(0, len(selected) - 1, count, dtype=np.int64)]
    if len(selected) < count:
        missing = np.setdiff1d(np.arange(n, dtype=np.int64), selected, assume_unique=False)
        selected = np.concatenate([selected, missing[: count - len(selected)]])
    return np.asarray(sorted(selected.tolist()), dtype=np.int64)


def _digest_value(values: np.ndarray) -> str:
    import hashlib
    return hashlib.sha256(np.asarray(values, dtype=np.float32).tobytes()).hexdigest()


def _live_encode(model_path: Path, texts: list[str], rows: np.ndarray, batch_size: int,
                 max_tokens: int, warmup: bool = False):
    """Encode rows with the pinned transformer and report measured GPU work."""
    import torch
    from transformers import AutoModel, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
    model = AutoModel.from_pretrained(model_path, local_files_only=True).cuda().eval().float()
    selected = [texts[int(row)] for row in rows]

    def encode_once(values):
        if torch.cuda.is_available():
            torch.cuda.synchronize()
            torch.cuda.reset_peak_memory_stats()
        started = time.monotonic()
        chunks = []
        raw_tokens = effective_tokens = 0
        with torch.inference_mode():
            for start in range(0, len(values), batch_size):
                batch = values[start:start + batch_size]
                raw = tokenizer(batch, padding=False, truncation=False,
                                add_special_tokens=True)["input_ids"]
                raw_tokens += sum(len(item) for item in raw)
                encoded = tokenizer(batch, padding=True, truncation=True,
                                    max_length=max_tokens, return_tensors="pt")
                effective_tokens += int(encoded["attention_mask"].sum().item())
                encoded = {key: value.cuda(non_blocking=True) for key, value in encoded.items()}
                hidden = model(**encoded).last_hidden_state
                mask = encoded["attention_mask"].unsqueeze(-1).to(hidden.dtype)
                pooled = (hidden * mask).sum(1) / mask.sum(1).clamp_min(1.0)
                chunks.append(torch.nn.functional.normalize(pooled, p=2, dim=1).float().cpu().numpy())
        if torch.cuda.is_available():
            torch.cuda.synchronize()
            peak_vram = int(torch.cuda.max_memory_allocated())
        else:
            peak_vram = 0
        values_out = np.concatenate(chunks, axis=0) if chunks else np.empty((0, 0), np.float32)
        elapsed = time.monotonic() - started
        return {
            "documents": len(values), "wall_seconds": elapsed,
            "documents_per_second": len(values) / elapsed if elapsed else None,
            "raw_tokens": int(raw_tokens), "effective_tokens": int(effective_tokens),
            "peak_vram_bytes": peak_vram, "peak_rss_bytes": _peak_rss_bytes(),
            "embedding_sha256": _digest_value(values_out),
        }

    if warmup and selected:
        encode_once(selected[: min(batch_size, len(selected))])
    records = [encode_once(selected) for _ in range(3)]
    model.to("cpu")
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    return records


def _load_calibration_checkpoint(root: Path):
    checkpoint = root / "runs/REV-02-fiqa-g_r_c-m17-t101/checkpoints/accessed-000002020"
    pools = json.loads((checkpoint / "calibration_pools.json").read_text())
    with np.load(checkpoint / "calibration_queries.npz", allow_pickle=False) as arrays:
        queries = dict(zip(arrays["query_ids"].tolist(), arrays["vectors"]))
    role_queries = {role: {str(qid): queries[str(qid)] for qid, _ in pool["pairs"]}
                    for role, pool in pools.items()}
    return checkpoint, pools, role_queries


def _remote_snapshot_bytes(root: Path):
    """Read verified E5 payload sizes without downloading another 50k graph."""
    manifest = next(root.glob(
        "runs/reviewer_inputs/e5_random_m17/runs/E5-scale-random-m17-t101-*/**/artifact_manifest.json"),
        None)
    if manifest is None:
        return {"status": "MISSING_LOCAL_ARTIFACT_MANIFEST"}
    data = json.loads(manifest.read_text())
    files = data.get("files", {})
    prefixes = ("checkpoints/bootstrap-", "checkpoints/accessed-")
    checkpoint_files = {name: int(meta["bytes"]) for name, meta in files.items()
                        if name.startswith(prefixes)}
    return {"status": "VERIFIED_LOCAL_MANIFEST", "source": str(manifest),
            "payload_id": data.get("payload_id"),
            "total_payload_bytes": int(sum(meta["bytes"] for meta in files.values())),
            "checkpoint_file_bytes": checkpoint_files,
            "snapshot_scope": "MS MARCO reduced 50k stored E5 snapshot"}


def run_benchmark(root: Path, cfg_path: Path, old_vectors: Path, new_vectors: Path,
                  old_queries: Path, new_queries: Path, model_path: Path,
                  live_sample: int = 4096, repeats: int = 3) -> dict:
    if repeats != 3:
        raise ValueError("REV-06 is preregistered with exactly three measured repeats")
    root = Path(root)
    cfg = load_config(cfg_path, root=root)
    cfg["execution"]["phase"] = "development"
    cfg["execution"]["require_target"] = False
    cfg["mapping"].update(kind="residual_mlp", regional="full")
    cfg["calibration"]["enabled"] = True
    cfg["scheduler"].update(kind="random", refit_fraction=0.05)
    cfg["search"].update(backend="exact", k=10, candidates=100)
    prepared = root / "data/processed/fiqa"
    manifest = validate_prepared(prepared)
    text_path = root / "runs/reviewer_inputs/fiqa_text/documents.jsonl"
    query_path = root / "runs/reviewer_inputs/fiqa_text/queries.jsonl"
    doc_ids, doc_texts = _load_jsonl(text_path)
    all_query_ids, all_query_texts = _load_jsonl(query_path)
    roles_json = json.loads((prepared / "splits/query_roles.json").read_text())
    query_ids = sorted(roles_json["roles"]["eval"])
    query_rows = np.asarray([all_query_ids.index(qid) for qid in query_ids], dtype=np.int64)
    query_texts = [all_query_texts[int(row)] for row in query_rows]
    prepared_ids = (prepared / "doc_ids.txt").read_text().splitlines()
    if doc_ids != prepared_ids:
        raise ValueError("FiQA document text/vector manifest is not aligned")
    old = np.load(old_vectors, mmap_mode="r")
    new = np.load(new_vectors, mmap_mode="r")
    old_q = np.load(old_queries, mmap_mode="r")
    new_q = np.load(new_queries, mmap_mode="r")
    if old.shape != (len(doc_ids), 384) or new.shape != (len(doc_ids), 768):
        raise ValueError("FiQA document vectors have unexpected dimensions")
    if (old_q.shape[0] != len(all_query_ids) or new_q.shape[0] != len(all_query_ids)
            or old_q.shape[1] != 384 or new_q.shape[1] != 768):
        raise ValueError("FiQA query vectors are not row-aligned")
    old_q = np.asarray(old_q[query_rows])
    new_q = np.asarray(new_q[query_rows])
    checkpoint, fixed_pools, calibration_queries = _load_calibration_checkpoint(root)
    pools = sample_document_pools(doc_ids, cfg)
    roles = {"train": pools["train"], "validation": pools["validation"],
             "backfill": np.arange(len(doc_ids), dtype=np.int64)}
    out = root / "runs/REV-06-fiqa-cost-m17"
    out.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    rows = []
    migration_repeats = []

    # One tiny warm-up exercises BLAS, map fit, and the exact index but is never
    # included in the reported repeats.
    warm_cfg = deepcopy(cfg)
    warm_accessor = PaidEmbeddingAccessor(lambda values: np.asarray(new[np.asarray(values)]), roles,
                                          len(doc_ids), mode="cached_access")
    warm_state = bootstrap_migration(doc_ids, pools, old, warm_accessor, warm_cfg,
                                     map_seed=17, traffic_seed=101,
                                     calibration_queries=calibration_queries,
                                     fixed_calibration_pools=fixed_pools)
    run_migration(warm_state, [max(len(warm_accessor.paid), int(.05 * len(doc_ids)))])
    warmup = {"status": "PASS", "paid": len(warm_accessor.paid),
              "rss_bytes": _peak_rss_bytes()}
    del warm_state, warm_accessor

    for repeat in range(1, repeats + 1):
        repeat_cfg = deepcopy(cfg)
        accessor = PaidEmbeddingAccessor(lambda values: np.asarray(new[np.asarray(values)]), roles,
                                          len(doc_ids), mode="cached_access")
        before = time.monotonic()
        state = bootstrap_migration(doc_ids, pools, old, accessor, repeat_cfg,
                                    map_seed=17, traffic_seed=101,
                                    calibration_queries=calibration_queries,
                                    fixed_calibration_pools=fixed_pools)
        bootstrap_wall = time.monotonic() - before
        state_events = run_migration(state, [int(np.ceil(.10 * len(doc_ids))),
                                             int(np.ceil(.25 * len(doc_ids)))])
        repeat_rows = [{"repeat": repeat, "phase": "bootstrap", "component": "bootstrap",
                        "wall_seconds": bootstrap_wall, "peak_rss_bytes": _peak_rss_bytes(),
                        "paid": len(accessor.paid), "backfilled": len(state.backfilled)}]
        for record in state.cost_records:
            repeat_rows.append({"repeat": repeat, "phase": "migration", **record,
                                "paid": len(accessor.paid), "backfilled": len(state.backfilled)})
        with tempfile.TemporaryDirectory(prefix=f"rev06-r{repeat}-") as temp:
            checkpoint_path = emit_checkpoint(state, Path(temp) / "checkpoints", "25pct",
                                              file_digest(root / "configs/base.yaml"))
            checkpoint_bytes = _recursive_bytes(checkpoint_path)
        migration_repeats.append({"repeat": repeat, "bootstrap_wall_seconds": bootstrap_wall,
                                  "events": state_events["events"], "cost_records": state.cost_records,
                                  "cached_access": dict(accessor.cost),
                                  "checkpoint_bytes": checkpoint_bytes,
                                  "peak_rss_bytes": _peak_rss_bytes(),
                                  "index_vector_bytes": int(state.index.vectors.nbytes),
                                  "index_fidelity_bytes": int(state.index.fidelity.nbytes)})
        rows.extend(repeat_rows)
        del state, accessor

    # Query-side control: use the already verified matched-budget MLP adapter.
    adapter_path = root / "runs/REV-01-fiqa-query-controls-m17-t101/checkpoints/query-side-residual_mlp/M0.safetensors"
    query_map = load_map_state(adapter_path)
    old_index = ExactIndex(np.asarray(old), doc_ids, np.ones(len(doc_ids), dtype=bool))
    import os
    os.environ["MIXINDEX_BATCH_EXACT"] = "1"
    query_records = []
    for batch_size in (1, 32):
        times = []
        for _ in range(3):
            started_q = time.monotonic()
            transformed = transform_global(query_map, np.asarray(new_q), normalize_output=True)
            if batch_size == 1:
                for start in range(0, len(transformed), batch_size):
                    old_index.search(transformed[start:start + batch_size], k=10)
            else:
                old_index.search(transformed, k=10)
            times.append(time.monotonic() - started_q)
        query_records.append({"batch_size": batch_size, "queries": len(query_ids),
                              "repeats": times, "median_seconds": float(np.median(times)),
                              "query_adapter": "query-side-residual_mlp-m17",
                              "cached_query_vectors": True})

    live_rows = _stratified_rows(doc_texts, live_sample)
    live_encode = _live_encode(model_path, doc_texts, live_rows, batch_size=4,
                               max_tokens=384, warmup=True)
    live_query_rows = _stratified_rows(query_texts, min(len(query_texts), 648))
    live_query_encode = _live_encode(model_path, query_texts, live_query_rows, batch_size=8,
                                     max_tokens=384, warmup=True)
    docs_per_second = [record["documents_per_second"] for record in live_encode if record["documents_per_second"]]
    estimated_full_seconds = float(len(doc_texts) / np.mean(docs_per_second)) if docs_per_second else None
    storage = {"fiqa": {
        "query_side_adapter_bytes": _recursive_bytes(adapter_path.parent),
        "cached_old_vectors_bytes": int(old.nbytes), "cached_new_vectors_bytes": int(new.nbytes),
        "cached_old_query_vectors_bytes": int(old_q.nbytes),
        "cached_new_query_vectors_bytes": int(new_q.nbytes),
        "migration_checkpoint_bytes": [item["checkpoint_bytes"] for item in migration_repeats],
    }, "stored_ms_marco50k_snapshot": _remote_snapshot_bytes(root)}
    timing = {"review_action": "REV-06", "warmup": warmup,
              "repeats": migration_repeats, "migration_rows": rows,
              "query_side": query_records,
        "live_target_encode": {"model_path": str(model_path), "sample_rows": len(live_rows),
                  "sample_row_sha256": _digest_value(np.asarray(new[live_rows])),
                  "records": live_encode, "estimated_full_fiqa_seconds": estimated_full_seconds,
                  "estimate_scope": "length-stratified sample; full-corpus estimate, not measured"},
              "live_query_encode": {"sample_rows": len(live_query_rows), "records": live_query_encode},
              "storage": storage, "exclusive": True, "performance_claim": False,
              "elapsed_seconds": time.monotonic() - started}
    write_json(out / "timing.json", timing)
    pq.write_table(pa.Table.from_pylist(rows), out / "metrics.parquet", compression="zstd")
    write_json(out / "config.lock.json", {"config": redacted_config(cfg), "reviewer": {
        "review_action": "REV-06", "warmup": 1, "measured_repeats": repeats,
        "migration_target_fraction": 0.25, "access_mode": "cached_access",
        "live_encode_sample": len(live_rows), "query_batches": [1, 32]}})
    write_json(out / "reference_inputs.json", {
        "dataset_manifest": manifest, "calibration_parent": str(checkpoint),
        "vectors": {"old": file_digest(old_vectors), "new": file_digest(new_vectors)},
        "queries": {"old": file_digest(old_queries), "new": file_digest(new_queries)},
        "query_side_adapter": file_digest(adapter_path),
        "model_path": str(model_path), "model_files": _recursive_bytes(model_path),
        "document_rows": len(doc_ids), "query_rows": len(query_ids),
        "live_encode_rows": live_rows.tolist(), "live_query_rows": live_query_rows.tolist(),
        "cached_vs_live": {"migration": "cached_access", "target_reference": "live_encode_sample",
                           "query_adapter": "cached_query_vectors"}})
    write_json(out / "reviewer_manifest.json", {"review_action": "REV-06",
        "analysis_only": False, "new_migration": False, "live_measurement": True,
        "hardware_scope": "NVIDIA H100 80GB HBM3 MIG 2g.20gb",
        "warmup": 1, "measured_repeats": repeats,
        "scopes": ["mapping_calibration", "migration_refit_remap", "query_side_adapter",
                   "live_target_encode", "storage"],
        "cached_vs_live": {"migration": "cached_access", "target_encode": "live_sample_estimate",
                           "query_vectors": "cached"},
        "parent_runs": ["REV-01-fiqa-query-controls-m17-t101",
                         "REV-02-fiqa-g_r_c-m17-t101"],
        "performance_claim": False})
    summary = {"compute_status": "COMPUTE_DONE", "outcome": "completed",
               "review_action": "REV-06", "documents": len(doc_ids),
               "evaluation_queries": len(query_ids), "measured_repeats": repeats,
               "warmup": 1, "live_encode_sample_documents": len(live_rows),
               "live_encode_full_estimate": estimated_full_seconds,
               "stored_ms_marco50k_snapshot_status": storage["stored_ms_marco50k_snapshot"]["status"],
               "exclusive": True, "performance_claim": False,
               "hardware_scope": "NVIDIA H100 80GB HBM3 MIG 2g.20gb"}
    write_json(out / "summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--config", type=Path, default=Path("configs/base.yaml"))
    parser.add_argument("--old-vectors", type=Path, required=True)
    parser.add_argument("--new-vectors", type=Path, required=True)
    parser.add_argument("--old-queries", type=Path, required=True)
    parser.add_argument("--new-queries", type=Path, required=True)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--live-sample", type=int, default=4096)
    args = parser.parse_args()
    result = run_benchmark(args.root, args.config, args.old_vectors, args.new_vectors,
                           args.old_queries, args.new_queries, args.model_path, args.live_sample)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["compute_status"] == "COMPUTE_DONE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
