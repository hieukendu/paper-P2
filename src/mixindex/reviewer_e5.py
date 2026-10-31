"""REV-04.E5 and REV-08 post-hoc evaluation of stored E5 HNSW snapshots.

The accepted reduced-scale E5 runs already contain the immutable serving graphs.
This analysis replays the graph snapshots against a pinned Arctic query encoder;
it does not rebuild a corpus, fit a mapper, or use aggregate ARR as a proxy for
per-query evidence.  Seen queries are the exact 5,000 schedule groups from the
common-scale manifest.  Held-out queries are ORCAS evaluation groups after
normalized-text disjointness is applied against schedule/calibration/tune
groups.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import resource
import time
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from .io import file_digest, write_json
from .reviewer_posthoc import overlap_at_k, rbo_extrapolated


CHECKPOINTS = (
    ("bootstrap", "bootstrap-000001750"),
    ("f_0.05", "accessed-000002500"),
    ("f_0.10", "accessed-000005000"),
    ("f_0.25", "accessed-000012500"),
    ("f_0.50", "accessed-000025000"),
    ("f_1.00", "accessed-000050000"),
)
E5_RE = re.compile(r"^E5-scale-(?P<scheduler>[a-z_]+)-m(?P<map_seed>\d+)-t(?P<traffic_seed>\d+)-")
EXPECTED_RUNS = (
    "E5-scale-random-m17-t101-59baabdbf9f2",
    "E5-scale-random-m29-t101-ca30a574a09c",
    "E5-scale-random-m43-t101-2cc4feda61a0",
    "E5-scale-degree-m17-t101-310142bb1ee2",
    "E5-scale-degree-m29-t101-ca194e98f844",
    "E5-scale-degree-m43-t101-49ef754eb2c6",
    "E5-scale-read-m17-t101-2f342e8fe56d",
    "E5-scale-read-m29-t101-019dd03645c4",
    "E5-scale-read-m43-t101-98c382eb2ba7",
    "E5-scale-greedy-m17-t101-29c55cf5dc0c",
    "E5-scale-greedy-m29-t101-87682640c62c",
    "E5-scale-greedy-m43-t101-b57b9d5f86c1",
)


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _peak_rss_bytes() -> int:
    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024)


def _find_payload(snapshot_root: Path, run_name: str, checkpoint_dir: str) -> Path:
    pattern = f"**/runs/{run_name}/*/checkpoints/{checkpoint_dir}/index/hnsw.bin"
    matches = sorted(snapshot_root.glob(pattern))
    if len(matches) != 1:
        raise FileNotFoundError(f"expected one local snapshot for {run_name}/{checkpoint_dir}, found {matches}")
    return matches[0].parent


def _find_payload_optional(snapshot_root: Path, run_name: str, checkpoint_dir: str) -> Path | None:
    pattern = f"**/runs/{run_name}/*/checkpoints/{checkpoint_dir}/index/hnsw.bin"
    matches = sorted(snapshot_root.glob(pattern))
    if len(matches) > 1:
        raise ValueError(f"duplicate local snapshots for {run_name}/{checkpoint_dir}")
    return matches[0].parent if matches else None


def _load_roles(roles_path: Path, manifest_path: Path) -> dict:
    roles = _json(roles_path)
    manifest = _json(manifest_path)
    common = manifest["common_scale"]
    schedule = [str(x) for x in common["orcas_group_ids"]]
    blocked = set(schedule)
    for role in ("cal_fit", "cal_check", "tune"):
        blocked.update(str(x) for x in roles["roles"].get(role, []))
    eval_ids = [str(x) for x in roles["roles"]["eval"]]
    return {
        "schedule": schedule,
        "blocked": blocked,
        "eval": eval_ids,
        "manifest": manifest,
        "roles": roles,
    }


def _read_query_rows(parquet_path: Path, wanted: set[str]) -> dict[str, dict]:
    """Read only requested groups without materializing the 10M-row table."""
    parquet = pq.ParquetFile(parquet_path)
    found: dict[str, dict] = {}
    for batch in parquet.iter_batches(
        batch_size=100_000,
        columns=["group_id", "normalized_text", "text", "representative_id", "source_query_count", "excluded_dev"],
    ):
        ids = batch.column("group_id").to_pylist()
        for index, group_id in enumerate(ids):
            group_id = str(group_id)
            if group_id not in wanted:
                continue
            found[group_id] = {
                "group_id": group_id,
                "normalized_text": str(batch.column("normalized_text")[index].as_py()),
                "text": str(batch.column("text")[index].as_py()),
                "representative_id": str(batch.column("representative_id")[index].as_py()),
                "source_query_count": int(batch.column("source_query_count")[index].as_py()),
                "excluded_dev": bool(batch.column("excluded_dev")[index].as_py()),
            }
    missing = wanted.difference(found)
    if missing:
        raise ValueError(f"ORCAS query rows missing for {len(missing)} requested groups")
    return found


def build_split(roles_path: Path, manifest_path: Path, queries_path: Path, output: Path) -> dict:
    roles = _load_roles(roles_path, manifest_path)
    wanted = set(roles["schedule"]) | set(roles["eval"]) | set(roles["blocked"])
    rows = _read_query_rows(queries_path, wanted)
    blocked_texts = {rows[group_id]["normalized_text"] for group_id in roles["blocked"] if group_id in rows}
    split_rows: list[dict] = []
    for group_id in roles["schedule"]:
        row = rows[group_id]
        split_rows.append({**row, "role": "seen", "disjoint": True})
    heldout_total = len(roles["eval"])
    excluded = 0
    for group_id in roles["eval"]:
        row = rows[group_id]
        disjoint = row["normalized_text"] not in blocked_texts
        if not disjoint:
            excluded += 1
            continue
        split_rows.append({**row, "role": "heldout", "disjoint": True})
    table = pa.Table.from_pylist(split_rows)
    output.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, output, compression="zstd")
    return {
        "split_path": str(output),
        "schedule_count": len(roles["schedule"]),
        "heldout_eval_total": heldout_total,
        "heldout_disjoint_count": heldout_total - excluded,
        "heldout_excluded_normalized_overlap": excluded,
        "blocked_group_count": len(roles["blocked"]),
        "orcas_release_hash": _json(queries_path.parent / "manifest.json")["release_hash"],
        "orcas_split_hash": roles["roles"]["hash"],
        "common_manifest_hash": roles["manifest"]["common_scale"]["manifest_hash"],
        "disjointness": "normalized_text(eval) not in normalized_text(schedule ∪ cal_fit ∪ cal_check ∪ tune)",
    }


def _encode_queries(model_path: Path, texts: list[str], batch_size: int = 32, max_tokens: int = 8192) -> tuple[np.ndarray, dict]:
    import torch
    from transformers import AutoModel, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
    model = AutoModel.from_pretrained(model_path, local_files_only=True).cuda().eval().float()
    values = [f"query: {text}" for text in texts]
    chunks = []
    raw_tokens = effective_tokens = 0
    started = time.monotonic()
    with torch.inference_mode():
        for start in range(0, len(values), batch_size):
            batch = values[start : start + batch_size]
            raw = tokenizer(batch, padding=False, truncation=False, add_special_tokens=True)["input_ids"]
            raw_tokens += sum(len(item) for item in raw)
            encoded = tokenizer(batch, padding=True, truncation=True, max_length=max_tokens, return_tensors="pt")
            effective_tokens += int(encoded["attention_mask"].sum().item())
            encoded = {key: value.cuda(non_blocking=True) for key, value in encoded.items()}
            hidden = model(**encoded).last_hidden_state
            pooled = hidden[:, 0, :]
            chunks.append(torch.nn.functional.normalize(pooled, p=2, dim=1).float().cpu().numpy())
    if torch.cuda.is_available():
        torch.cuda.synchronize()
    vectors = np.concatenate(chunks, axis=0).astype(np.float32, copy=False)
    record = {
        "model_path": str(model_path),
        "query_prefix": "query: ",
        "pooling": "cls",
        "max_tokens": max_tokens,
        "batch_size": batch_size,
        "rows": int(len(vectors)),
        "dim": int(vectors.shape[1]),
        "raw_tokens": int(raw_tokens),
        "effective_tokens": int(effective_tokens),
        "wall_seconds": time.monotonic() - started,
        "peak_vram_bytes": int(torch.cuda.max_memory_allocated()) if torch.cuda.is_available() else 0,
        "peak_rss_bytes": _peak_rss_bytes(),
        "vectors_sha256": _sha256_bytes(vectors.tobytes()),
    }
    model.to("cpu")
    del model, tokenizer
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    return vectors, record


def _query_graph(index_dir: Path, query_vectors: np.ndarray, ids: np.ndarray, k: int = 10) -> tuple[np.ndarray, np.ndarray]:
    import hnswlib

    index_meta = _json(index_dir / "index.json")
    dimension = int(index_meta.get("dim", index_meta.get("dimension", query_vectors.shape[1])))
    index = hnswlib.Index(space="cosine", dim=dimension)
    index.load_index(str(index_dir / "hnsw.bin"), max_elements=len(ids))
    if hasattr(index, "set_num_threads"):
        index.set_num_threads(4)
    index.set_ef(int(index_meta.get("parameters", {}).get("ef_search", 2000)))
    labels, distances = index.knn_query(query_vectors, k=k)
    return np.asarray(ids[labels]), np.asarray(distances, dtype=np.float32)


def _metrics(current: list[str], target: list[str]) -> dict:
    return {
        "overlap_at_1": overlap_at_k(current, target, 1),
        "overlap_at_3": overlap_at_k(current, target, 3),
        "overlap_at_10": overlap_at_k(current, target, 10),
        "rbo_ext_10": rbo_extrapolated(current, target, 10, 0.9),
    }


def run(root: Path, snapshot_root: Path, roles_path: Path, manifest_path: Path, queries_path: Path,
        model_path: Path, output: Path, batch_size: int = 32) -> dict:
    started = time.monotonic()
    output.mkdir(parents=True, exist_ok=True)
    split = build_split(roles_path, manifest_path, queries_path, output / "selection.parquet")
    selection = pq.read_table(output / "selection.parquet").to_pylist()
    query_ids = [str(row["group_id"]) for row in selection]
    query_texts = [str(row["text"]) for row in selection]
    query_roles = {str(row["group_id"]): str(row["role"]) for row in selection}
    query_vectors, encode_record = _encode_queries(model_path, query_texts, batch_size=batch_size)
    if query_vectors.shape[0] != len(selection) or query_vectors.shape[1] != 1024:
        raise ValueError(f"unexpected query vector shape {query_vectors.shape}")

    metrics: list[dict] = []
    ranking_records: list[tuple[str, str, str, np.ndarray, np.ndarray]] = []
    cell_summaries: list[dict] = []
    run_dirs = {p.name: p for p in snapshot_root.iterdir() if p.is_dir() and p.name.startswith("E5-scale-")}
    unexpected = set(run_dirs) - set(EXPECTED_RUNS)
    if unexpected:
        raise ValueError(f"unexpected local E5 cells: {sorted(unexpected)}")
    missing_cells: list[dict] = []
    for run_name in EXPECTED_RUNS:
        run_dir = run_dirs.get(run_name)
        if run_dir is None:
            missing_cells.append({"run_name": run_name, "status": "NOT_AVAILABLE_LOCAL"})
            continue
        match = E5_RE.match(run_dir.name)
        if not match:
            raise ValueError(f"cannot parse E5 run name {run_dir.name}")
        scheduler = match.group("scheduler")
        map_seed = int(match.group("map_seed"))
        traffic_seed = int(match.group("traffic_seed"))
        checkpoint_rankings: dict[str, np.ndarray] = {}
        checkpoint_distances: dict[str, np.ndarray] = {}
        missing_checkpoints: list[str] = []
        for checkpoint, checkpoint_dir in CHECKPOINTS:
            index_dir = _find_payload_optional(snapshot_root, run_dir.name, checkpoint_dir)
            if index_dir is None:
                missing_checkpoints.append(checkpoint)
                continue
            ids = np.load(index_dir / "ids.npy", allow_pickle=False)
            labels, distances = _query_graph(index_dir, query_vectors, ids)
            checkpoint_rankings[checkpoint] = labels
            checkpoint_distances[checkpoint] = distances
            print(f"replayed {run_dir.name} {checkpoint} queries={len(query_vectors)}", flush=True)
        if missing_checkpoints or "f_1.00" not in checkpoint_rankings:
            missing_cells.append({
                "run_name": run_dir.name,
                "status": "NOT_REPLAYABLE_COMPACT_STATE_ONLY" if missing_checkpoints else "NOT_REPLAYABLE_NO_TARGET",
                "missing_checkpoints": missing_checkpoints,
            })
            continue
        target = checkpoint_rankings["f_1.00"]
        for checkpoint, _ in CHECKPOINTS:
            current = checkpoint_rankings[checkpoint]
            distances = checkpoint_distances[checkpoint]
            for row_index, (query_id, role) in enumerate(zip(query_ids, (query_roles[q] for q in query_ids))):
                current_list = [str(x) for x in current[row_index].tolist()]
                target_list = [str(x) for x in target[row_index].tolist()]
                values = _metrics(current_list, target_list)
                metrics.append({
                    "row_type": "per_query",
                    "review_action": "REV-04.E5",
                    "run_name": run_dir.name,
                    "scheduler": scheduler,
                    "map_seed": map_seed,
                    "traffic_seed": traffic_seed,
                    "checkpoint": checkpoint,
                    "role": role,
                    "query_id": query_id,
                    "target_reference": "same_cell_f_1.00_stored_hnsw",
                    "ranking_source": "stored_hnsw_knn_query",
                    "distance_at_1": float(distances[row_index, 0]),
                    **values,
                })
                ranking_records.append((run_dir.name, checkpoint, role, np.asarray(current[row_index]), np.asarray(distances[row_index])))
            for role in ("seen", "heldout"):
                subset = [row for row in metrics if row["run_name"] == run_dir.name and row["checkpoint"] == checkpoint and row["role"] == role]
                cell_summaries.append({
                    "run_name": run_dir.name,
                    "scheduler": scheduler,
                    "map_seed": map_seed,
                    "traffic_seed": traffic_seed,
                    "checkpoint": checkpoint,
                    "role": role,
                    "query_count": len(subset),
                    "mean_overlap_at_10": float(np.mean([row["overlap_at_10"] for row in subset])),
                    "mean_rbo_ext_10": float(np.mean([row["rbo_ext_10"] for row in subset])),
                })

    metrics_table = pa.Table.from_pylist(metrics)
    pq.write_table(metrics_table, output / "metrics.parquet", compression="zstd")
    # A compact TREC file preserves all top-10 rankings and HNSW distances while
    # avoiding a second uncompressed ranking artifact.
    counters: dict[tuple[str, str, str], int] = {}
    query_lists = {
        role: [query_id for query_id in query_ids if query_roles[query_id] == role]
        for role in ("seen", "heldout")
    }
    with gzip.open(output / "retrieval.trec.gz", "wt", encoding="utf-8") as handle:
        for run_name, checkpoint, role, labels, distances in ranking_records:
            key = (run_name, checkpoint, role)
            index = counters.get(key, 0)
            counters[key] = index + 1
            qid = query_lists[role][index]
            for rank, (doc_id, distance) in enumerate(zip(labels.tolist(), distances.tolist()), 1):
                handle.write(f"{qid} Q0 {doc_id} {rank} {1.0 - float(distance):.8f} {run_name}:{checkpoint}\n")

    summary = {
        "review_action": "REV-04.E5",
        "compute_status": "COMPUTE_DONE",
        "outcome": "analysis_complete",
        "analysis_only": True,
        "performance_claim": False,
        "snapshot_cells_expected": len(EXPECTED_RUNS),
        "snapshot_cells_available": len(EXPECTED_RUNS) - len(missing_cells),
        "missing_cells": missing_cells,
        "checkpoints_per_cell": len(CHECKPOINTS),
        "per_query_rows": len(metrics),
        "split": split,
        "query_encoder": encode_record,
        "ranking_source": "stored_hnsw_knn_query",
        "target_reference": "same_cell_f_1.00_stored_hnsw",
        "hardware_scope": "NVIDIA H100 80GB HBM3 MIG 2g.20gb",
        "elapsed_seconds": time.monotonic() - started,
        "peak_rss_bytes": _peak_rss_bytes(),
    }
    write_json(output / "summary.json", summary)
    write_json(output / "timing.json", {"elapsed_seconds": summary["elapsed_seconds"], "query_encoder": encode_record,
                                         "snapshot_cells_expected": len(EXPECTED_RUNS),
                                         "snapshot_cells_available": len(EXPECTED_RUNS) - len(missing_cells),
                                         "missing_cells": missing_cells,
                                         "checkpoints": [x[0] for x in CHECKPOINTS]})
    write_json(output / "reference_inputs.json", {
        "review_action": "REV-04.E5",
        "orcas_roles_path": str(roles_path),
        "orcas_queries_path": str(queries_path),
        "common_scale_manifest_path": str(manifest_path),
        "common_scale_manifest_sha256": file_digest(manifest_path),
        "query_encoder": encode_record,
        "snapshot_root": str(snapshot_root),
        "ranking_source": "stored_hnsw_knn_query",
        "target_reference": "same_cell_f_1.00_stored_hnsw",
        "no_aggregate_arr_used": True,
        "cell_summaries": cell_summaries,
    })
    write_json(output / "reviewer_manifest.json", {
        "review_action": "REV-04.E5",
        "metric_schema": {
            "overlap": "|top_k(current) intersection top_k(target)| / k",
            "rbo": "(1-p) sum(p^(d-1) A_d) + p^K A_K",
            "rbo_p": 0.9,
            "depths": [1, 3, 10],
        },
        "split": split,
        "query_vector_sha256": encode_record["vectors_sha256"],
        "snapshot_cells_expected": len(EXPECTED_RUNS),
        "snapshot_cells_available": len(EXPECTED_RUNS) - len(missing_cells),
        "missing_cells": missing_cells,
        "checkpoints": [x[0] for x in CHECKPOINTS],
        "ranking_source": "stored_hnsw_knn_query",
    })
    write_json(output / "config.lock.json", {
        "review_action": "REV-04.E5",
        "analysis_only": True,
        "batch_size": batch_size,
        "checkpoints": [x[0] for x in CHECKPOINTS],
        "model": "Snowflake/snowflake-arctic-embed-l-v2.0",
        "pooling": "cls",
        "query_prefix": "query: ",
        "max_tokens": 8192,
        "hnsw_ef_search": 2000,
        "target_reference": "same_cell_f_1.00_stored_hnsw",
        "performance_claim": False,
    })
    return summary


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-root", type=Path, required=True)
    parser.add_argument("--roles", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--queries", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=32)
    return parser


def main() -> int:
    args = _parser().parse_args()
    print(json.dumps(run(args.output.parent.parent.parent, args.snapshot_root, args.roles, args.manifest,
                         args.queries, args.model, args.output, args.batch_size), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
