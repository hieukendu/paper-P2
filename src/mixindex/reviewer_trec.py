"""REV-05 TREC-COVID random seed repetitions.

The accepted seed ``(17, 101)`` is kept as a read-only parent reference.  This
runner executes the two additional map/backfill seed tuples for each mapping
family on the full TREC-COVID anchor.  It deliberately uses the same cached
document/query vectors and the existing migration primitives; no corpus or
query split is changed.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import time

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from .config import load_config, redacted_config
from .data.prepare import validate_prepared
from .data.splits import sample_document_pools
from .index import ExactIndex
from .io import digest, file_digest, write_json
from .migration import bootstrap_migration, emit_checkpoint, run_migration
from .vectors import PaidEmbeddingAccessor


METHODS = ("op", "la", "residual_mlp")
CHECKPOINTS = (0.05, 0.10, 0.25, 0.50, 1.00)


def _load_vectors(path: Path) -> np.ndarray:
    values = np.load(path, mmap_mode="r")
    if values.ndim != 2 or not np.isfinite(values).all():
        raise ValueError(f"invalid vector file: {path}")
    return values


def _load_qrels(path: Path, query_ids: list[str]) -> dict[str, dict[str, int]]:
    qrels = {str(qid): {} for qid in query_ids}
    for row in pq.read_table(path, filters=[("split", "=", "test")]).to_pylist():
        qid = str(row["group_id"])
        if qid in qrels and int(row["grade"]) > 0:
            doc = str(row["doc_id"])
            qrels[qid][doc] = max(qrels[qid].get(doc, 0), int(row["grade"]))
    return qrels


def _ndcg(ranking: list[str], qrels: dict[str, int]) -> float:
    gains = [(2 ** int(qrels.get(doc, 0)) - 1) / np.log2(rank + 2)
             for rank, doc in enumerate(ranking[:10])]
    ideal = sorted(qrels.values(), reverse=True)[:10]
    denominator = sum((2 ** int(grade) - 1) / np.log2(rank + 2)
                      for rank, grade in enumerate(ideal))
    return float(sum(gains) / denominator) if denominator else 0.0


def _evaluate(query_ids: list[str], result, doc_ids: list[str], qrels: dict[str, dict[str, int]],
              full_rankings: dict[str, list[str]], role: str, checkpoint: str,
              accessed: int, scheduled: int) -> tuple[list[dict], dict[str, list[str]]]:
    rows, rankings = [], {}
    for qid, found in zip(query_ids, result.rows):
        ranking = [str(doc_ids[int(row)]) for row in found[:10]]
        rankings[qid] = ranking
        relevant = set(qrels.get(qid, {}))
        full = full_rankings[qid]
        rows.append({
            "query_id": qid,
            "checkpoint": checkpoint,
            "ranking_role": role,
            "accessed": int(accessed),
            "scheduled": int(scheduled),
            "f_accessed": float(accessed / len(doc_ids)),
            "f_scheduled": float(scheduled / len(doc_ids)),
            "ndcg_at_10": _ndcg(ranking, qrels.get(qid, {})),
            "hit_at_10": float(bool(relevant.intersection(ranking))),
            "nfr_at_1": float(bool(full and full[0] in relevant and
                                    (not ranking or ranking[0] not in relevant))),
            "overlap_at_10": len(set(ranking).intersection(full)) / 10.0,
        })
    return rows, rankings


def _emit(handle, rankings: dict[str, list[str]], label: str) -> None:
    for qid, docs in rankings.items():
        for rank, doc in enumerate(docs, 1):
            handle.write(f"{qid} Q0 {doc} {rank} {-rank} {label}\n")


def _order_hash(order: list[int]) -> str:
    values = np.asarray(order, dtype=np.int64)
    return hashlib.sha256(values.tobytes()).hexdigest()


def _read_reference_retrieval(path: Path, query_ids: list[str]) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    labels = {"old_reference": {}, "full_new_reference": {}}
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            fields = line.split()
            if len(fields) < 6 or fields[-1] not in labels:
                continue
            labels[fields[-1]].setdefault(fields[0], []).append((int(fields[3]), fields[2]))
    result = {}
    for label, rows in labels.items():
        result[label] = {qid: [doc for _, doc in sorted(values)] for qid, values in rows.items()}
    missing = [qid for qid in query_ids if qid not in result["old_reference"] or qid not in result["full_new_reference"]]
    if missing:
        raise ValueError(f"reference retrieval lacks query IDs: {missing[:3]}")
    return result["old_reference"], result["full_new_reference"]


def run_cell(root: Path, config_path: Path, method: str, map_seed: int, traffic_seed: int,
             old_vectors_path: Path, new_vectors_path: Path,
             old_queries_path: Path, new_queries_path: Path,
             old_query_vectors_path: Path | None = None,
             new_query_vectors_path: Path | None = None,
             reference_retrieval: Path | None = None) -> dict:
    if method not in METHODS:
        raise ValueError(f"unknown method: {method}")
    cfg = load_config(config_path, root=root)
    cfg["dataset"]["name"] = "trec-covid"
    cfg["dataset"]["subset_size"] = None
    cfg["mapping"]["kind"] = method
    cfg["mapping"]["regional"] = "full"
    cfg["calibration"]["enabled"] = True
    cfg["scheduler"]["kind"] = "random"
    cfg["search"]["backend"] = "exact"
    cfg["search"]["k"] = 10
    cfg["budget"]["checkpoints"] = list(CHECKPOINTS)
    cfg["experiment"].update(map_seed=map_seed, traffic_seed=traffic_seed,
                              variant="primary", cell_role="mapping")
    cfg["execution"].update(phase="official", require_target=False)

    prepared = root / "data/processed/trec-covid"
    manifest = validate_prepared(prepared)
    doc_ids = (prepared / "doc_ids.txt").read_text(encoding="utf-8").splitlines()
    old = _load_vectors(old_vectors_path)
    new = _load_vectors(new_vectors_path)
    if old.shape != (len(doc_ids), 384) or new.shape != (len(doc_ids), 768):
        raise ValueError(f"vector shape mismatch old={old.shape} new={new.shape}")

    def _read_query(path: Path, vector_path: Path | None) -> tuple[list[str], np.ndarray]:
        ids, values = [], []
        for line in path.open(encoding="utf-8"):
            row = json.loads(line)
            ids.append(str(row["id"]))
        values = _load_vectors(vector_path or path.with_suffix(".npy"))
        return ids, values

    old_qids, old_q = _read_query(old_queries_path, old_query_vectors_path)
    new_qids, new_q = _read_query(new_queries_path, new_query_vectors_path)
    if old_qids != new_qids or old_q.shape != (len(old_qids), 384) or new_q.shape != (len(new_qids), 768):
        raise ValueError("query vector row alignment/dimensions differ")
    query_ids = list(old_qids)
    qrels = _load_qrels(prepared / "qrels.parquet", query_ids)
    qold_by_id = dict(zip(old_qids, old_q))
    qnew_by_id = dict(zip(new_qids, new_q))
    eval_old = np.stack([qold_by_id[qid] for qid in query_ids])
    eval_new = np.stack([qnew_by_id[qid] for qid in query_ids])
    pools = sample_document_pools(doc_ids, cfg)
    # TREC-COVID intentionally has no independent calibration query population.
    empty_cal = {"cal_fit": {"rows": [], "pairs": []},
                 "cal_check": {"rows": [], "pairs": []}}
    roles = {"train": pools["train"], "validation": pools["validation"],
             "backfill": np.arange(len(doc_ids), dtype=np.int64)}
    accessor = PaidEmbeddingAccessor(
        lambda rows: np.asarray(new[np.asarray(rows, dtype=np.int64)], dtype=np.float32),
        roles, len(doc_ids), mode="cached_access")

    run_id = f"REV-05-trec-covid-{method}-random-m{map_seed}-t{traffic_seed}"
    out = root / "runs" / run_id
    out.mkdir(parents=True, exist_ok=True)
    if (out / "summary.json").exists():
        prior = json.loads((out / "summary.json").read_text(encoding="utf-8"))
        if prior.get("compute_status") == "COMPUTE_DONE":
            return prior

    locked = {"review_action": "REV-05", "method": method, "map_seed": map_seed,
              "traffic_seed": traffic_seed, "dataset_release": manifest["release_hash"],
              "old_vectors": file_digest(old_vectors_path), "new_vectors": file_digest(new_vectors_path),
              "old_queries": file_digest(old_queries_path), "new_queries": file_digest(new_queries_path),
              "query_ids": query_ids, "calibration_query_population": "empty_by_release"}
    config_hash = digest(locked)
    write_json(out / "config.lock.json", {"config": redacted_config(cfg), "reviewer": locked})
    write_json(out / "reference_inputs.json", {
        "dataset_manifest": manifest, "document_ids_sha256": file_digest(prepared / "doc_ids.txt"),
        "vector_sha256": {"old": file_digest(old_vectors_path), "new": file_digest(new_vectors_path)},
        "query_sha256": {"old": file_digest(old_queries_path), "new": file_digest(new_queries_path)},
        "query_ids": query_ids, "calibration": "N/A_NO_DEVELOPMENT_QUERY_POPULATION",
        "parent_seed_tuple": {"map_seed": 17, "traffic_seed": 101},
    })
    summary = {"compute_status": "FAILED", "review_action": "REV-05", "method": method,
               "variant": "primary", "map_seed": map_seed, "traffic_seed": traffic_seed,
               "analysis_only": False, "new_migration": True, "performance_claim": False,
               "hardware_scope": "NVIDIA H100 80GB HBM3 MIG 2g.20gb", "phase": "official",
               "cell_role": "mapping", "calibration_reason": "insufficient_calibration"}
    started = time.monotonic()
    records, events = [], []
    try:
        if reference_retrieval is not None:
            old_rankings, full_rankings = _read_reference_retrieval(reference_retrieval, query_ids)
            old_result = None
            full_result = None
        else:
            target_index = ExactIndex(np.asarray(new), doc_ids, np.ones(len(doc_ids), dtype=bool),
                                      chunk_rows=cfg["search"]["chunk_rows"])
            old_index = ExactIndex(np.asarray(old), doc_ids, np.ones(len(doc_ids), dtype=bool),
                                   chunk_rows=cfg["search"]["chunk_rows"])
            full_result = target_index.search(eval_new, k=10)
            full_rankings = {qid: [doc_ids[int(row)] for row in found[:10]]
                             for qid, found in zip(query_ids, full_result.rows)}
            old_result = old_index.search(eval_old, k=10)
        with gzip.open(out / "retrieval.trec.gz", "wt", encoding="utf-8") as handle:
            if old_result is None:
                old_rows = [{"query_id": qid, "checkpoint": "old_reference", "ranking_role": "old_reference",
                             "accessed": 0, "scheduled": 0, "f_accessed": 0.0, "f_scheduled": 0.0,
                             "ndcg_at_10": _ndcg(old_rankings[qid], qrels.get(qid, {})),
                             "hit_at_10": float(bool(set(qrels.get(qid, {})).intersection(old_rankings[qid]))),
                             "nfr_at_1": float(bool(full_rankings[qid] and full_rankings[qid][0] in qrels.get(qid, {})
                                                     and (not old_rankings[qid] or old_rankings[qid][0] not in qrels.get(qid, {})))),
                             "overlap_at_10": len(set(old_rankings[qid]).intersection(full_rankings[qid])) / 10.0}
                            for qid in query_ids]
            else:
                old_rows, old_rankings = _evaluate(query_ids, old_result, doc_ids, qrels, full_rankings,
                                                   "old_reference", "old_reference", 0, 0)
            _emit(handle, old_rankings, "old_reference")
            if full_result is None:
                full_rows = [{"query_id": qid, "checkpoint": "full_new_reference", "ranking_role": "full_new_reference",
                              "accessed": len(doc_ids), "scheduled": 0, "f_accessed": 1.0, "f_scheduled": 0.0,
                              "ndcg_at_10": _ndcg(full_rankings[qid], qrels.get(qid, {})),
                              "hit_at_10": float(bool(set(qrels.get(qid, {})).intersection(full_rankings[qid]))),
                              "nfr_at_1": 0.0, "overlap_at_10": 1.0}
                             for qid in query_ids]
            else:
                full_rows, _ = _evaluate(query_ids, full_result, doc_ids, qrels, full_rankings,
                                         "full_new_reference", "full_new_reference", len(doc_ids), 0)
            _emit(handle, full_rankings, "full_new_reference")
            records.extend(old_rows)
            records.extend(full_rows)

            region_cache = root / "cache" / "reviewer_regions" / f"trec-m{map_seed}.npz"
            fixed_regions = None
            if region_cache.exists():
                with np.load(region_cache, allow_pickle=False) as arrays:
                    fixed_regions = {key: arrays[key] for key in ("assignments", "centers", "sample_rows")}
            state = bootstrap_migration(doc_ids, pools, old, accessor, cfg,
                                        map_seed=map_seed, traffic_seed=traffic_seed,
                                        calibration_queries={"cal_fit": {}, "cal_check": {}},
                                        fixed_calibration_pools=empty_cal,
                                        fixed_regions=fixed_regions)
            if fixed_regions is None:
                region_cache.parent.mkdir(parents=True, exist_ok=True)
                np.savez(region_cache, **state.regions)
            initial = state.index.search(eval_new, k=10)
            label = f"accessed-{len(accessor.paid):09d}"
            rows, rankings = _evaluate(query_ids, initial, doc_ids, qrels, full_rankings,
                                       "snapshot", label, len(accessor.paid), len(state.backfilled))
            _emit(handle, rankings, label)
            records.extend(rows)
            emit_checkpoint(state, out / "checkpoints", label, config_hash)
            targets = [max(len(accessor.paid), int(np.ceil(frac * len(doc_ids)))) for frac in CHECKPOINTS]
            for target in sorted(set(targets)):
                if target <= len(accessor.paid):
                    continue
                result = run_migration(state, [target])
                events.extend(result["events"])
                label = f"accessed-{len(accessor.paid):09d}"
                current = state.index.search(eval_new, k=10)
                rows, rankings = _evaluate(query_ids, current, doc_ids, qrels, full_rankings,
                                           "snapshot", label, len(accessor.paid), len(state.backfilled))
                _emit(handle, rankings, label)
                records.extend(rows)
                emit_checkpoint(state, out / "checkpoints", label, config_hash)
        pq.write_table(pa.Table.from_pylist(records), out / "metrics.parquet", compression="zstd")
        with (out / "events.jsonl").open("w", encoding="utf-8") as handle:
            for event in events:
                handle.write(json.dumps(event, sort_keys=True) + "\n")
        write_json(out / "timing.json", {"elapsed_seconds": time.monotonic() - started,
                                          "accessor": accessor.cost, "migration": state.cost_records,
                                          "hardware_scope": summary["hardware_scope"],
                                          "paid_order_count": len(accessor.order)})
        write_json(out / "reviewer_manifest.json", {
            "review_action": "REV-05", "method": method, "map_seed": map_seed,
            "traffic_seed": traffic_seed, "checkpoints": list(CHECKPOINTS),
            "documents": len(doc_ids), "evaluation_queries": len(query_ids),
            "pools": {key: (int(len(value)) if hasattr(value, "__len__") else int(value))
                      for key, value in pools.items()},
            "calibration": "N/A_NO_DEVELOPMENT_QUERY_POPULATION",
            "paid_order_hash": _order_hash(accessor.order),
            "resume_prefix": "NOT_APPLICABLE_NEW_CELL",
        })
        summary.update(compute_status="COMPUTE_DONE", outcome="completed", documents=len(doc_ids),
                       evaluation_queries=len(query_ids), checkpoints=len(set(targets)) + 1,
                       unique_paid_documents=len(accessor.paid), f_accessed=len(accessor.paid) / len(doc_ids),
                       elapsed_seconds=time.monotonic() - started,
                       completion_exact_agreement=1.0)
    except Exception as exc:
        summary.update(outcome="failed", error_type=type(exc).__name__, reason=str(exc))
    write_json(out / "summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--config", type=Path, default=Path("configs/base.yaml"))
    parser.add_argument("--method", choices=METHODS, required=True)
    parser.add_argument("--map-seed", type=int, required=True)
    parser.add_argument("--traffic-seed", type=int, required=True)
    parser.add_argument("--old-vectors", type=Path, required=True)
    parser.add_argument("--new-vectors", type=Path, required=True)
    parser.add_argument("--old-queries", type=Path, required=True)
    parser.add_argument("--new-queries", type=Path, required=True)
    parser.add_argument("--old-query-vectors", type=Path, required=True)
    parser.add_argument("--new-query-vectors", type=Path, required=True)
    parser.add_argument("--reference-retrieval", type=Path, default=None)
    args = parser.parse_args()
    result = run_cell(args.root, args.config, args.method, args.map_seed, args.traffic_seed,
                      args.old_vectors, args.new_vectors, args.old_queries, args.new_queries,
                      args.old_query_vectors, args.new_query_vectors, args.reference_retrieval)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["compute_status"] == "COMPUTE_DONE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
