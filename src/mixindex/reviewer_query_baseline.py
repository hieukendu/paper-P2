"""REV-01 matched query-side/forward controls on the FiQA anchor."""

from __future__ import annotations

import argparse
from copy import deepcopy
import gzip
import json
from pathlib import Path
import time
from types import SimpleNamespace

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from .config import load_config, redacted_config
from .data.prepare import validate_prepared
from .data.splits import sample_document_pools
from .index import ExactIndex
from .io import file_digest, write_json
from .maps import fit_global_map, save_map_state, transform_global


METHODS = ("op", "la", "residual_mlp")


def _search_exact_batched(index, query_vectors, k=10, batch_size=32):
    """Exact top-k with the same tie-break as ExactIndex, but batched GEMM.

    The reviewer control needs the same full exact index and IDs.  Calling the
    reference implementation one query at a time is needlessly slow for the
    repeated six-cell matched-refit grid, so keep its row/tie semantics while
    batching only the score matrix multiplication.
    """
    queries = np.asarray(query_vectors, dtype=np.float32)
    count = min(k + 1, len(index.ids))
    rows = []
    scores_out = []
    for start in range(0, len(queries), batch_size):
        batch = queries[start:start + batch_size]
        scores = index.vectors @ batch.T
        for column in range(len(batch)):
            values = scores[:, column]
            all_rows = np.arange(len(index.ids), dtype=np.int64)
            if len(all_rows) > count:
                threshold = np.partition(values, len(values) - count)[-count]
                keep = np.flatnonzero(values >= threshold)
            else:
                keep = np.arange(len(all_rows))
            order = np.lexsort((index.id_order[keep], -values[keep]))[:count]
            chosen = keep[order]
            rows.append(chosen)
            scores_out.append(values[chosen])
    return SimpleNamespace(rows=np.asarray(rows), scores=np.asarray(scores_out))


def _load(path: Path, vectors: Path):
    ids = [json.loads(line)["id"] for line in path.open(encoding="utf-8")]
    return ids, np.load(vectors, mmap_mode="r")


def _qrels(path, eval_ids):
    result = {qid: {} for qid in eval_ids}
    for row in pq.read_table(path, filters=[("split", "=", "test")]).to_pylist():
        if row["group_id"] in result and int(row["grade"]) > 0:
            result[row["group_id"]][row["doc_id"]] = max(result[row["group_id"]].get(row["doc_id"], 0), int(row["grade"]))
    return result


def ndcg(ranking, qrels):
    values = [(2 ** int(qrels.get(doc, 0)) - 1) / np.log2(rank + 2) for rank, doc in enumerate(ranking[:10])]
    ideal = sorted(qrels.values(), reverse=True)[:10]
    denominator = sum((2 ** int(g) - 1) / np.log2(i + 2) for i, g in enumerate(ideal))
    return float(sum(values) / denominator) if denominator else 0.0


def evaluate(qids, result, ids, qrels, full_rankings, label, role):
    rows, rankings = [], {}
    for qid, found in zip(qids, result.rows):
        ranking = [str(ids[int(row)]) for row in found[:10]]
        rankings[qid] = ranking
        relevant = set(qrels.get(qid, {}))
        full = full_rankings[qid]
        rows.append({"query_id": qid, "checkpoint": label, "ranking_role": role,
                     "ndcg_at_10": ndcg(ranking, qrels.get(qid, {})),
                     "hit_at_10": float(bool(relevant.intersection(ranking))),
                     "overlap_at_10": len(set(ranking).intersection(full)) / 10.0})
    return rows, rankings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--config", type=Path, default=Path("configs/base.yaml"))
    parser.add_argument("--old-vectors", type=Path, required=True)
    parser.add_argument("--new-vectors", type=Path, required=True)
    parser.add_argument("--old-queries", type=Path, required=True)
    parser.add_argument("--new-queries", type=Path, required=True)
    parser.add_argument("--map-seed", type=int, default=17)
    args = parser.parse_args()
    root = args.root
    cfg = load_config(args.config, root=root)
    cfg["mapping"]["kind"] = "residual_mlp"
    prepared = root / "data/processed/fiqa"
    manifest = validate_prepared(prepared)
    ids_old, old = _load(root / "runs/reviewer_inputs/fiqa_text/documents.jsonl", args.old_vectors)
    ids_new, new = _load(root / "runs/reviewer_inputs/fiqa_text/documents.jsonl", args.new_vectors)
    if ids_old != ids_new or old.shape != (len(ids_old), 384) or new.shape != (len(ids_new), 768):
        raise ValueError("vector row alignment/dimensions differ")
    qids_old, old_q = _load(root / "runs/reviewer_inputs/fiqa_text/queries.jsonl", args.old_queries)
    qids_new, new_q = _load(root / "runs/reviewer_inputs/fiqa_text/queries.jsonl", args.new_queries)
    roles = json.loads((prepared / "splits/query_roles.json").read_text())["roles"]
    train = np.array(sorted(set(range(len(ids_old))) - set()), dtype=np.int64)
    pools = sample_document_pools(ids_old, cfg)
    eval_ids = sorted(roles["eval"])
    train_rows, val_rows = pools["train"], pools["validation"]
    qold = {qid: old_q[qids_old.index(qid)] for qid in eval_ids}
    qnew = {qid: new_q[qids_new.index(qid)] for qid in eval_ids}
    qrels = _qrels(prepared / "qrels.parquet", eval_ids)
    full_index = ExactIndex(np.asarray(new), ids_new, np.ones(len(ids_new), dtype=bool))
    old_index = ExactIndex(np.asarray(old), ids_old, np.ones(len(ids_old), dtype=bool))
    full_result = _search_exact_batched(full_index, np.stack([qnew[q] for q in eval_ids]), k=10)
    _, full_rankings = evaluate(eval_ids, full_result, ids_new, qrels,
                                {q: [ids_new[int(r)] for r in row[:10]] for q, row in zip(eval_ids, full_result.rows)},
                                "full_new_reference", "full_new_reference")
    old_result = _search_exact_batched(old_index, np.stack([qold[q] for q in eval_ids]), k=10)
    rows, old_rankings = evaluate(eval_ids, old_result, ids_old, qrels, full_rankings, "old_reference", "old_reference")
    result_rows = rows + [{**r, "checkpoint": "full_new_reference", "ranking_role": "full_new_reference"}
                          for r in evaluate(eval_ids, full_result, ids_new, qrels, full_rankings,
                                             "full_new_reference", "full_new_reference")[0]]
    out = root / "runs" / f"REV-01-fiqa-query-controls-m{args.map_seed}-t101"
    out.mkdir(parents=True, exist_ok=True)
    with gzip.open(out / "retrieval.trec.gz", "wt", encoding="utf-8") as handle:
        for label, ranking in (("old_reference", old_rankings), ("full_new_reference", full_rankings)):
            for qid, docs in ranking.items():
                for rank, doc in enumerate(docs, 1):
                    handle.write(f"{qid} Q0 {doc} {rank} {-rank} {label}\n")
    checkpoints = []
    timing_records = []
    control_rankings = []
    for method in METHODS:
        # Forward/global control: fit old->new on the same paired train/val rows.
        fit_started = time.monotonic()
        forward, f_record = fit_global_map(method, (old[train_rows], new[train_rows]),
                                            (old[val_rows], new[val_rows]), cfg["mapping"], args.map_seed)
        forward_path = out / "checkpoints" / f"forward-global-{method}" / "M0.safetensors"
        forward_path.parent.mkdir(parents=True, exist_ok=True)
        save_map_state(forward, forward_path)
        timing_records.append({"scope": f"forward_global_{method}",
                               "fit_seconds": time.monotonic() - fit_started,
                               "train_rows": len(train_rows), "validation_rows": len(val_rows)})
        checkpoints.append({"label": f"forward_global_{method}", "direction": "old_to_new",
                            "path": str(forward_path.relative_to(out)), "fit_record": f_record})
        mapped = transform_global(forward, np.asarray(old), normalize_output=True)
        forward_index = ExactIndex(mapped, ids_old, np.ones(len(ids_old), dtype=bool))
        f_result = _search_exact_batched(forward_index, np.stack([qnew[q] for q in eval_ids]), k=10)
        f_rows, f_rankings = evaluate(eval_ids, f_result, ids_old, qrels, full_rankings,
                                      f"forward_global_{method}", "forward_global")
        result_rows.extend(f_rows)
        control_rankings.append((f"forward_global_{method}", f_rankings))
        # Query-side/new->old uses the identical paired document pool and the old index.
        fit_started = time.monotonic()
        query_map, q_record = fit_global_map(method, (new[train_rows], old[train_rows]),
                                             (new[val_rows], old[val_rows]), cfg["mapping"], args.map_seed)
        query_path = out / "checkpoints" / f"query-side-{method}" / "M0.safetensors"
        query_path.parent.mkdir(parents=True, exist_ok=True)
        save_map_state(query_map, query_path)
        timing_records.append({"scope": f"query_side_{method}",
                               "fit_seconds": time.monotonic() - fit_started,
                               "train_rows": len(train_rows), "validation_rows": len(val_rows)})
        checkpoints.append({"label": f"query_side_{method}", "direction": "new_to_old",
                            "path": str(query_path.relative_to(out)), "fit_record": q_record})
        adapted_q = transform_global(query_map, np.stack([qnew[q] for q in eval_ids]), normalize_output=True)
        q_result = _search_exact_batched(old_index, adapted_q, k=10)
        q_rows, q_rankings = evaluate(eval_ids, q_result, ids_old, qrels, full_rankings,
                                      f"query_side_{method}", "query_side")
        result_rows.extend(q_rows)
        control_rankings.append((f"query_side_{method}", q_rankings))
        if method == METHODS[-1]:
            records = {"forward_global": f_record, "query_side": q_record}
    with gzip.open(out / "retrieval.trec.gz", "at", encoding="utf-8") as handle:
        for label, rankings in control_rankings:
            for qid, docs in rankings.items():
                for rank, doc in enumerate(docs, 1):
                    handle.write(f"{qid} Q0 {doc} {rank} {-rank} {label}\n")
    pq.write_table(pa.Table.from_pylist(result_rows), out / "metrics.parquet", compression="zstd")
    write_json(out / "config.lock.json", {"config": redacted_config(cfg), "reviewer": {
        "review_action": "REV-01", "map_seed": args.map_seed, "traffic_seed": 101,
        "directions": ["query_side_new_to_old", "forward_global_old_to_new"],
        "paired_train_rows": len(train_rows), "paired_validation_rows": len(val_rows),
        "fit_records": records}})
    write_json(out / "reference_inputs.json", {"dataset_manifest": manifest, "vector_sha256": {
        "old": file_digest(args.old_vectors), "new": file_digest(args.new_vectors)},
        "query_sha256": {"old": file_digest(args.old_queries), "new": file_digest(args.new_queries)},
        "query_ids": eval_ids})
    write_json(out / "reviewer_manifest.json", {"review_action": "REV-01", "directions": [
        "query_side_new_to_old", "forward_global_old_to_new"], "methods": list(METHODS),
        "paired_train_rows": len(train_rows), "paired_validation_rows": len(val_rows),
        "checkpoint_level_weights": checkpoints,
        "access_cost_latency_nfr_rbo": {"actual_accessed_documents": 0,
                                         "training_pool_documents": int(len(train_rows)),
                                         "rbo_source": "retrieval.trec.gz; run reviewer_posthoc.py",
                                         "latency_source": "timing.json"},
        "performance_claim": False})
    write_json(out / "summary.json", {"compute_status": "COMPUTE_DONE", "outcome": "completed",
        "review_action": "REV-01", "analysis_only": False, "new_migration": True,
        "map_seed": args.map_seed, "traffic_seed": 101, "documents": len(ids_old),
        "evaluation_queries": len(eval_ids), "configurations": 6,
        "hardware_scope": "NVIDIA H100 80GB HBM3 MIG 2g.20gb", "performance_claim": False})
    write_json(out / "timing.json", {"mode": "matched_refit_posthoc", "records": timing_records,
                                      "training_pool_documents": len(train_rows),
                                      "validation_pool_documents": len(val_rows),
                                      "performance_claim": False})
    print(json.dumps(json.loads((out / "summary.json").read_text()), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
