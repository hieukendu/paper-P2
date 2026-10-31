"""Reviewer REV-02/REV-03 quality cells on the frozen FiQA anchor.

This is a deliberately small supplemental runner around the existing migration
primitives.  It uses the same document pools, calibration roles, exact index,
random traffic seed and budget checkpoints; only the declared global/regional/
calibration intervention changes between cells.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import asdict
import gzip
import json
from pathlib import Path
import tempfile
import time

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from .config import load_config, redacted_config
from .calibration import fit_score_calibration
from .data.prepare import validate_prepared
from .data.splits import sample_document_pools
from .index import ExactIndex
from .io import file_digest, write_json
from .maps import map_documents, save_map_state
from .migration import (bootstrap_migration, emit_checkpoint,
                        refresh_scheduling_snapshot, run_migration)
from .scheduling import SchedulingTraffic
from .vectors import PaidEmbeddingAccessor


VARIANTS = {
    "G_R_C": {"kind": "residual_mlp", "regional": "full", "calibration": True},
    "G_R_0": {"kind": "residual_mlp", "regional": "full", "calibration": False},
    "G_0_C": {"kind": "residual_mlp", "regional": "none", "calibration": True},
    "G_0_0": {"kind": "residual_mlp", "regional": "none", "calibration": False},
    "Gfixed_R_C": {"kind": "fixed_projection", "regional": "full", "calibration": True},
    "Gfixed_0_0": {"kind": "fixed_projection", "regional": "none", "calibration": False},
}

SENSITIVITY_VARIANTS = {
    "rho05_safe": {"radius_multiplier": 0.5, "safety": True},
    "rho05_unsafe": {"radius_multiplier": 0.5, "safety": False},
    "rho1_safe": {"radius_multiplier": 1.0, "safety": True},
    "rho1_unsafe": {"radius_multiplier": 1.0, "safety": False},
    "rho2_safe": {"radius_multiplier": 2.0, "safety": True},
    "rho2_unsafe": {"radius_multiplier": 2.0, "safety": False},
    "uncertainty_proxy": {"radius_multiplier": 1.0, "safety": True},
}

TRANSITION_VARIANTS = {
    "OP": {"kind": "op", "regional": "full", "calibration": True},
    "MLP": {"kind": "residual_mlp", "regional": "full", "calibration": True},
}


def _load_jsonl_vectors(path: Path, vector_path: Path) -> tuple[list[str], np.ndarray]:
    ids = []
    for line in path.open(encoding="utf-8"):
        ids.append(json.loads(line)["id"])
    return ids, np.load(vector_path, mmap_mode="r")


def _qrels(path: Path, eval_groups: set[str]) -> dict[str, dict[str, int]]:
    result = {qid: {} for qid in eval_groups}
    for row in pq.read_table(path, filters=[("split", "=", "test")]).to_pylist():
        if row["group_id"] in result and int(row["grade"]) > 0:
            result[row["group_id"]][row["doc_id"]] = max(result[row["group_id"]].get(row["doc_id"], 0), int(row["grade"]))
    return result


def _ndcg(ranking: list[str], qrels: dict[str, int]) -> float:
    gains = [(2 ** int(qrels.get(doc, 0)) - 1) / np.log2(rank + 2) for rank, doc in enumerate(ranking[:10])]
    ideal = sorted(qrels.values(), reverse=True)[:10]
    denominator = sum((2 ** int(grade) - 1) / np.log2(rank + 2) for rank, grade in enumerate(ideal))
    return float(sum(gains) / denominator) if denominator else 0.0


def _rows_for_result(query_ids, result, ids, qrels, full_rankings, old=False):
    rows, rankings = [], {}
    for qid, found in zip(query_ids, result.rows):
        ranking = [str(ids[int(row)]) for row in found[:10]]
        rankings[qid] = ranking
        relevant = set(qrels.get(qid, {}))
        full = full_rankings[qid]
        rows.append({
            "query_id": qid,
            "ndcg_at_10": _ndcg(ranking, qrels.get(qid, {})),
            "hit_at_10": float(bool(relevant.intersection(ranking))),
            "nfr_at_1": float(bool(full and full[0] in relevant and (not ranking or ranking[0] not in relevant))),
            "overlap_at_10": len(set(ranking).intersection(full)) / 10.0,
            "ranking_role": "old_reference" if old else "snapshot",
        })
    return rows, rankings


def _emit_rankings(handle, rankings, label):
    for qid, docs in rankings.items():
        for rank, doc in enumerate(docs, 1):
            handle.write(f"{qid} Q0 {doc} {rank} {-rank} {label}\n")


def _emit_reviewer_state(state, output, checkpoint_id, config_hash):
    """Write a compact learned-state checkpoint for reviewer ablations.

    The accepted migration checkpoint format stores the complete 57k-document
    index at every prefix.  For the 18-cell reviewer ablation grid that would
    duplicate tens of GB of unchanged vectors.  These state-only checkpoints
    preserve the learned map, regional sufficient statistics, calibration
    pools, paid order, RNG/cost marker, and fidelity metadata; one full
    restoreable checkpoint is retained in the representative m17 bundle.
    """
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    destination = output / checkpoint_id
    if destination.exists():
        marker = json.loads((destination / "checkpoint.json").read_text())
        if marker["config_hash"] != config_hash or marker["backfilled"] != len(state.backfilled):
            raise ValueError("Checkpoint path already contains a different prefix")
        return destination
    temp = Path(tempfile.mkdtemp(prefix=f".{checkpoint_id}-", dir=output))
    save_map_state(state.M0, temp / "M0.safetensors")
    np.savez(temp / "state.npz", regional=state.regional,
             H=state.statistics.H, B=state.statistics.B, counts=state.statistics.counts,
             stats_seen=np.array(sorted(state.statistics.seen), dtype=np.int64),
             dirty=np.array(sorted(state.statistics.dirty), dtype=np.int64),
             centers=state.regions["centers"], assignments=state.regions["assignments"],
             sample_rows=state.regions["sample_rows"],
             backfilled=np.array(state.backfilled, dtype=np.int64),
             paid_order=np.array(state.accessor.order, dtype=np.int64),
             heldout=np.array(sorted(state.heldout), dtype=np.int64))
    write_json(temp / "calibration_pools.json", state.calibration_pools)
    query_ids = sorted(state.calibration_queries)
    np.savez(temp / "calibration_queries.npz", query_ids=np.array(query_ids, dtype=str),
             vectors=np.stack([state.calibration_queries[q] for q in query_ids]) if query_ids else
             np.empty((0, state.index.vectors.shape[1]), dtype=np.float32))
    write_json(temp / "index_metadata.json", {
        "backend": "exact", "epoch": state.index.epoch,
        "rows": len(state.index.ids), "dimension": int(state.index.vectors.shape[1]),
        "calibration": asdict(state.index.calibration),
        "fidelity_count": int(state.index.fidelity.sum()),
    })
    files = {str(p.relative_to(temp)): file_digest(p) for p in temp.rglob("*") if p.is_file()}
    marker = {"complete": True, "format": "reviewer_state_only_v1",
              "config_hash": config_hash, "next_refit": state.next_refit,
              "backfilled": len(state.backfilled), "paid": len(state.accessor.paid),
              "rng": state.rng.bit_generator.state, "cost_records": state.cost_records,
              "read_state": state.read_state, "accessor_cost": state.accessor.cost,
              "files": files}
    write_json(temp / "checkpoint.json", marker)
    temp.rename(destination)
    return destination


def _fit_uncertainty_proxy(state):
    """Fit the preregistered per-region cal-fit score-residual proxy."""
    pairs = state.calibration_pools["cal_fit"]["pairs"]
    if len(pairs) < 20:
        raise ValueError("INSUFFICIENT_SIGNAL: fewer than 20 cal-fit pairs")
    rows = np.asarray([int(row) for _, row in pairs], dtype=np.int64)
    qids = [str(qid) for qid, _ in pairs]
    queries = np.stack([state.calibration_queries[qid] for qid in qids])
    shadow = map_documents(rows, state.old_vectors, state.M0, state.regional,
                           state.regions["assignments"])
    target = np.stack([state.accessor.cache[int(row)] for row in rows])
    s = np.sum(queries * shadow, axis=1)
    t = np.sum(queries * target, axis=1)
    calibration = fit_score_calibration(s, t)
    residual = t - (calibration.a * s + calibration.b)
    global_std = float(np.std(residual))
    assignments = np.asarray(state.regions["assignments"], dtype=np.int64)
    radii, region_rows = [], []
    for region in range(len(state.regions["centers"])):
        local = residual[assignments[rows] == region]
        use_global = len(local) < 20
        value = float(np.std(local)) if not use_global else global_std
        radii.append(max(value, 1e-6))
        region_rows.append({"region": region, "pairs": int(len(local)),
                            "std": value, "source": "global_cal_fit_std" if use_global
                            else "region_cal_fit_std"})
    return {"status": "SIGNAL_OK", "formula": "cal_fit_score_residual_std_min20",
            "calibration": {"a": calibration.a, "b": calibration.b},
            "global_std": global_std, "radius_by_region": radii,
            "regions": region_rows, "pairs": int(len(pairs))}


def run_cell(cfg_path: Path, root: Path, variant: str, map_seed: int, traffic_seed: int,
             vectors_old: Path, vectors_new: Path, query_old: Path, query_new: Path,
             calibration_checkpoint: Path, review_action: str | None = None,
             scheduler_kind: str = "random", pair_tag: str | None = None) -> dict:
    is_sensitivity = variant in SENSITIVITY_VARIANTS
    is_transition = variant in TRANSITION_VARIANTS
    if variant not in VARIANTS and not is_sensitivity and not is_transition:
        raise ValueError(f"unknown reviewer variant {variant}")
    spec = (TRANSITION_VARIANTS[variant] if is_transition else VARIANTS[variant]) if not is_sensitivity else {
        "kind": "residual_mlp", "regional": "full", "calibration": True}
    review_action = review_action or ("REV-03" if is_sensitivity else "REV-02")
    if scheduler_kind not in {"random", "read", "greedy"}:
        raise ValueError(f"unsupported scheduler kind {scheduler_kind}")
    cfg = load_config(cfg_path, root=root)
    cfg["execution"]["phase"] = "development"
    cfg["execution"]["require_target"] = False
    cfg["experiment"].update(map_seed=map_seed, traffic_seed=traffic_seed, variant=variant)
    cfg["mapping"].update(kind=spec["kind"], regional=spec["regional"])
    cfg["calibration"]["enabled"] = spec["calibration"]
    cfg["scheduler"]["kind"] = "greedy" if is_sensitivity else scheduler_kind
    if is_sensitivity:
        cfg["reviewer"] = {
            "radius_multiplier": SENSITIVITY_VARIANTS[variant]["radius_multiplier"],
            "safety": SENSITIVITY_VARIANTS[variant]["safety"],
        }
        if variant == "uncertainty_proxy":
            cfg["reviewer"]["uncertainty_proxy"] = True
    cfg["search"].update(backend="exact", k=10, candidates=100)
    cfg["budget"]["checkpoints"] = [0.05, 0.10, 0.25]

    prepared = root / "data/processed/fiqa"
    manifest = validate_prepared(prepared)
    doc_ids = (prepared / "doc_ids.txt").read_text().splitlines()
    ids_old, old = _load_jsonl_vectors(root / "runs/reviewer_inputs/fiqa_text/documents.jsonl", vectors_old)
    ids_new, new = _load_jsonl_vectors(root / "runs/reviewer_inputs/fiqa_text/documents.jsonl", vectors_new)
    if (ids_old != doc_ids or ids_new != doc_ids or old.ndim != 2 or new.ndim != 2
            or old.shape[0] != len(doc_ids) or new.shape[0] != len(doc_ids)):
        raise ValueError("document vector rows/dimensions differ from prepared FiQA")
    qids_old, old_q = _load_jsonl_vectors(root / "runs/reviewer_inputs/fiqa_text/queries.jsonl", query_old)
    qids_new, new_q = _load_jsonl_vectors(root / "runs/reviewer_inputs/fiqa_text/queries.jsonl", query_new)
    roles = json.loads((prepared / "splits/query_roles.json").read_text())["roles"]
    eval_ids = sorted(roles["eval"])
    qold_by_id = dict(zip(qids_old, old_q))
    qnew_by_id = dict(zip(qids_new, new_q))
    qold = {qid: qold_by_id[qid] for qid in eval_ids}
    qnew = {qid: qnew_by_id[qid] for qid in eval_ids}
    eval_new = np.stack([qnew[qid] for qid in eval_ids])
    eval_old = np.stack([qold[qid] for qid in eval_ids])
    labels = _qrels(prepared / "qrels.parquet", set(eval_ids))

    checkpoint = Path(calibration_checkpoint)
    pools = json.loads((checkpoint / "calibration_pools.json").read_text())
    with np.load(checkpoint / "calibration_queries.npz", allow_pickle=False) as arrays:
        flat_queries = dict(zip(arrays["query_ids"].tolist(), arrays["vectors"]))
    # The checkpoint stores a deduplicated flat query-vector table, while the
    # calibration validator needs the role partition to enforce fit/check
    # disjointness.  Reconstruct that partition from the immutable pair lists.
    cal_queries = {"cal_fit": {}, "cal_check": {}}
    for role in ("cal_fit", "cal_check"):
        for qid, _ in pools[role]["pairs"]:
            if str(qid) not in flat_queries:
                raise ValueError(f"Calibration checkpoint lacks query vector {qid}")
            cal_queries[role][str(qid)] = flat_queries[str(qid)]
    base_pools = sample_document_pools(doc_ids, cfg)
    roles_for_accessor = {"train": base_pools["train"], "validation": base_pools["validation"],
                           "backfill": np.arange(len(doc_ids), dtype=np.int64)}
    source = lambda rows: np.asarray(new[np.asarray(rows, dtype=np.int64)], dtype=np.float32)
    accessor = PaidEmbeddingAccessor(source, roles_for_accessor, len(doc_ids), mode="cached_access")
    # Regional assignments depend only on the frozen old-vector snapshot and
    # map seed.  Reuse the immutable parent partition for the seed17 smoke and
    # cache each newly fitted seed so the six ablation variants do not refit
    # K-means repeatedly.
    region_prefix = f"{review_action}-{pair_tag}" if pair_tag else "REV-02"
    region_cache = root / "cache" / "reviewer_regions" / f"{region_prefix}-fiqa-m{map_seed}.npz"
    fixed_regions = None
    if spec["regional"] != "none":
        if region_cache.exists():
            with np.load(region_cache, allow_pickle=False) as arrays:
                fixed_regions = {key: arrays[key] for key in ("assignments", "centers", "sample_rows")}
        elif map_seed == 17 and pair_tag is None:
            parent_state = checkpoint / "state.npz"
            if parent_state.exists():
                with np.load(parent_state, allow_pickle=False) as arrays:
                    fixed_regions = {key: arrays[key] for key in ("assignments", "centers", "sample_rows")}
    locked = {"review_action": review_action, "variant": variant, "scheduler_kind": scheduler_kind,
              "pair_tag": pair_tag, "map_seed": map_seed,
              "traffic_seed": traffic_seed, "dataset_release": manifest["release_hash"],
              "vectors_old": file_digest(vectors_old), "vectors_new": file_digest(vectors_new),
              "calibration_checkpoint": str(checkpoint)}
    if pair_tag:
        run_id = f"{review_action}-{pair_tag}-fiqa-{variant.lower()}-{scheduler_kind}-m{map_seed}-t{traffic_seed}"
    else:
        run_id = f"{review_action}-fiqa-{variant.lower()}-m{map_seed}-t{traffic_seed}"
    run_dir = root / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    # Raw REV-02/03 bundles were initially produced before checkpoint-state
    # emission was wired in.  Treat a summary without checkpoint markers as an
    # incomplete scientific artifact and rerun in place so the same run ID
    # gets a complete, restoreable payload before its HF receipt is refreshed.
    if (run_dir / "summary.json").exists() and list((run_dir / "checkpoints").glob("*/checkpoint.json")):
        return json.loads((run_dir / "summary.json").read_text())
    write_json(run_dir / "config.lock.json", {"config": redacted_config(cfg), "reviewer": locked})
    traffic = None
    if is_sensitivity or scheduler_kind == "read":
        schedule_ids = sorted(roles["schedule"])
        traffic = SchedulingTraffic(tuple(schedule_ids),
                                    np.stack([qnew_by_id[qid] for qid in schedule_ids]),
                                    proxies=None, role="schedule")
    write_json(run_dir / "reference_inputs.json", {"dataset_manifest": manifest, "parent_checkpoint": str(checkpoint),
        "vector_metadata": {"old": str(vectors_old), "new": str(vectors_new)}, "query_ids": eval_ids,
        "scheduler_traffic": (None if traffic is None else {"query_groups": len(traffic.query_ids),
                           "fingerprint": traffic.fingerprint, "role": traffic.role})})
    started = time.monotonic()
    summary = {"compute_status": "FAILED", "review_action": review_action, "variant": variant,
               "map_seed": map_seed, "traffic_seed": traffic_seed, "analysis_only": False,
               "new_migration": True, "performance_claim": False,
               "hardware_scope": "NVIDIA H100 80GB HBM3 MIG 2g.20gb"}
    records, retrieval = [], []
    try:
        target_index = ExactIndex(np.asarray(new), doc_ids, np.ones(len(doc_ids), dtype=bool), chunk_rows=cfg["search"]["chunk_rows"])
        old_index = ExactIndex(np.asarray(old), doc_ids, np.ones(len(doc_ids), dtype=bool), chunk_rows=cfg["search"]["chunk_rows"])
        full_result = target_index.search(eval_new, k=10)
        old_result = old_index.search(eval_old, k=10)
        full_rows, full_rankings = _rows_for_result(
            eval_ids, full_result, doc_ids, labels,
            {qid: [doc_ids[int(row)] for row in found[:10]] for qid, found in zip(eval_ids, full_result.rows)},
            old=False)
        old_rows, old_rankings = _rows_for_result(eval_ids, old_result, doc_ids, labels, full_rankings, old=True)
        records.extend([{**row, "checkpoint": "old_reference", "accessed": 0, "f_accessed": 0.0,
                         "f_scheduled": 0.0} for row in old_rows])
        records.extend([{**row, "checkpoint": "full_new_reference", "accessed": len(doc_ids),
                         "f_accessed": 1.0, "f_scheduled": 0.0, "ranking_role": "full_new_reference"}
                        for row in full_rows])
        state = bootstrap_migration(doc_ids, base_pools, old, accessor, cfg, map_seed=map_seed,
                                    traffic_seed=traffic_seed, calibration_queries=cal_queries,
                                    fixed_calibration_pools=pools, fixed_regions=fixed_regions)
        proxy_evidence = None
        if variant == "uncertainty_proxy":
            proxy_evidence = _fit_uncertainty_proxy(state)
            cfg["reviewer"]["radius_by_region"] = proxy_evidence["radius_by_region"]
            state.cfg["reviewer"]["radius_by_region"] = proxy_evidence["radius_by_region"]
            write_json(run_dir / "proxy.json", proxy_evidence)
        if (spec["regional"] != "none" and fixed_regions is None and
                not region_cache.exists()):
            region_cache.parent.mkdir(parents=True, exist_ok=True)
            np.savez(region_cache, **state.regions)
        config_hash = file_digest(run_dir / "config.lock.json")
        checkpoint_root = run_dir / "checkpoints"
        checkpoint_paths = []
        with gzip.open(run_dir / "retrieval.trec.gz", "wt", encoding="utf-8") as handle:
            _emit_rankings(handle, old_rankings, "old_reference")
            _emit_rankings(handle, full_rankings, "full_new_reference")
            initial = state.index.search(eval_new, k=10)
            rows, rankings = _rows_for_result(eval_ids, initial, doc_ids, labels, full_rankings)
            label = f"accessed-{len(accessor.paid):09d}"
            _emit_rankings(handle, rankings, label)
            if map_seed == 17 and variant == "G_R_C":
                checkpoint_paths.append(emit_checkpoint(state, checkpoint_root, label, config_hash))
            else:
                checkpoint_paths.append(_emit_reviewer_state(state, checkpoint_root, label, config_hash))
            records.extend([{**row, "checkpoint": label, "accessed": len(accessor.paid),
                             "f_accessed": len(accessor.paid) / len(doc_ids),
                             "f_scheduled": len(state.backfilled) / len(doc_ids)} for row in rows])
            targets = [max(len(accessor.paid), int(np.ceil(f * len(doc_ids)))) for f in cfg["budget"]["checkpoints"]]
            scheduling_cache = {}

            def cached_scheduling_refresh(current_state):
                # Greedy candidate sets are a fixed snapshot until the next
                # configured refit boundary.  Recomputing all 4,400 schedule
                # queries for every small backfill batch is redundant and
                # changes only runtime, not the locked rho/safety condition.
                key = int(current_state.next_refit)
                if key not in scheduling_cache:
                    scheduling_cache[key] = refresh_scheduling_snapshot(current_state, traffic)
                return scheduling_cache[key]

            for target in sorted(set(targets)):
                if target <= len(accessor.paid):
                    continue
                result = run_migration(state, [target], traffic=traffic,
                                       scheduling_refresh=(cached_scheduling_refresh if traffic is not None else None))
                label = f"accessed-{len(accessor.paid):09d}"
                current = state.index.search(eval_new, k=10)
                rows, rankings = _rows_for_result(eval_ids, current, doc_ids, labels, full_rankings)
                _emit_rankings(handle, rankings, label)
                if map_seed == 17 and variant == "G_R_C":
                    checkpoint_paths.append(emit_checkpoint(state, checkpoint_root, label, config_hash))
                else:
                    checkpoint_paths.append(_emit_reviewer_state(state, checkpoint_root, label, config_hash))
                records.extend([{**row, "checkpoint": label, "accessed": len(accessor.paid),
                                 "f_accessed": len(accessor.paid) / len(doc_ids),
                                 "f_scheduled": len(state.backfilled) / len(doc_ids)} for row in rows])
        pq.write_table(pa.Table.from_pylist(records), run_dir / "metrics.parquet", compression="zstd")
        write_json(run_dir / "timing.json", {"elapsed_seconds": time.monotonic() - started,
            "accessor": accessor.cost, "migration": state.cost_records, "hardware_scope": summary["hardware_scope"]})
        write_json(run_dir / "reviewer_manifest.json", {"review_action": review_action, "variant": variant,
            "map_seed": map_seed, "traffic_seed": traffic_seed, "checkpoints": cfg["budget"]["checkpoints"],
            "pools": {k: int(len(v)) if hasattr(v, "__len__") else v for k, v in base_pools.items()},
            "parent_checkpoint": str(checkpoint), "hardware_scope": summary["hardware_scope"],
            "scheduler": cfg["scheduler"]["kind"], "reviewer": cfg.get("reviewer"),
            "traffic": (None if traffic is None else {"query_groups": len(traffic.query_ids),
                       "fingerprint": traffic.fingerprint, "role": traffic.role}),
            "checkpoint_level_state": [str(path.relative_to(run_dir)) for path in checkpoint_paths],
            "checkpoint_format": ("full_restore_v1" if map_seed == 17 and variant == "G_R_C"
                                   else "reviewer_state_only_v1"),
            "uncertainty_proxy": (None if proxy_evidence is None else {
                "formula": proxy_evidence["formula"], "status": proxy_evidence["status"],
                "pairs": proxy_evidence["pairs"]})})
        summary.update(compute_status="COMPUTE_DONE", outcome="completed", documents=len(doc_ids),
                       evaluation_queries=len(eval_ids), checkpoints=len(checkpoint_paths),
                       unique_paid_documents=len(accessor.paid), f_accessed=len(accessor.paid) / len(doc_ids),
                       elapsed_seconds=time.monotonic() - started)
    except Exception as exc:
        summary.update(outcome="failed", error_type=type(exc).__name__, reason=str(exc))
    write_json(run_dir / "summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/base.yaml"))
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--variant", choices=sorted({*VARIANTS, *SENSITIVITY_VARIANTS}), required=True)
    parser.add_argument("--map-seed", type=int, required=True)
    parser.add_argument("--traffic-seed", type=int, default=101)
    parser.add_argument("--old-vectors", type=Path, required=True)
    parser.add_argument("--new-vectors", type=Path, required=True)
    parser.add_argument("--old-queries", type=Path, required=True)
    parser.add_argument("--new-queries", type=Path, required=True)
    parser.add_argument("--calibration-checkpoint", type=Path, required=True)
    parser.add_argument("--review-action", default=None)
    parser.add_argument("--scheduler-kind", choices=("random", "read", "greedy"), default="random")
    parser.add_argument("--pair-tag", default=None)
    args = parser.parse_args()
    result = run_cell(args.config, args.root, args.variant, args.map_seed, args.traffic_seed,
                      args.old_vectors, args.new_vectors, args.old_queries, args.new_queries,
                      args.calibration_checkpoint, review_action=args.review_action,
                      scheduler_kind=args.scheduler_kind, pair_tag=args.pair_tag)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["compute_status"] == "COMPUTE_DONE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
