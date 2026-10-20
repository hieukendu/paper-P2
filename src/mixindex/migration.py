"""Shared bootstrap/backfill loop with complete, verifiable restart checkpoints."""

from dataclasses import dataclass, field
import math
from pathlib import Path
import tempfile

import numpy as np

from .calibration import (Calibration, make_calibration_proposal, refresh_calibration,
                          validate_calibration_pools)
from .index import ExactIndex, HnswIndex, load_index
from .io import file_digest, read_json, write_json
from .maps import (RegionalStatistics, fit_global_map, fit_op, fit_regions, load_map_state,
                   map_documents, save_map_state, transform_global)
from .scheduling import (build_candidate_sets, choose_batch_cap, select_degree, select_greedy,
                         select_on_read, select_random)


@dataclass
class MigrationState:
    index: ExactIndex
    M0: object
    regions: dict
    statistics: RegionalStatistics
    regional: np.ndarray
    accessor: object
    old_vectors: np.ndarray
    rng: object
    backfilled: list
    heldout: set
    cfg: dict
    next_refit: int
    cost_records: list
    calibration_pools: dict = field(default_factory=lambda: {
        role: {"rows": [], "pairs": []} for role in ("cal_fit", "cal_check")})
    calibration_queries: dict = field(default_factory=dict)
    read_state: dict = field(default_factory=lambda: {"cursor": 0, "pending": []})


def bootstrap_migration(doc_ids, pools, old_vectors, paid_accessor, cfg, map_seed=17,
                        traffic_seed=101, calibration_queries=None, fixed_calibration_pools=None):
    from .runtime import cost_scope
    costs = []
    with cost_scope("bootstrap", costs):
        n = len(doc_ids)
        train, validation = pools["train"], pools["validation"]
        bootstrap_cap = len(train) + len(validation) + 2 * pools.get("cal_cap", 0)
        y_train = paid_accessor.request(train, "train", bootstrap_cap)
        y_val = paid_accessor.request(validation, "validation", bootstrap_cap)
        calibration_queries = calibration_queries or {"cal_fit": {}, "cal_check": {}}
        caps = {role: pools.get("cal_cap", 0) for role in ("cal_fit", "cal_check")}
        reserved = set(map(int, train)) | set(map(int, validation))
        if fixed_calibration_pools is not None:
            cal_pools = fixed_calibration_pools
        elif any(calibration_queries.values()):
            with cost_scope("common_op_calibration_proposal", costs):
                proposal = fit_op(old_vectors[train], y_train)
                cal_pools = make_calibration_proposal(
                    proposal, calibration_queries, old_vectors, doc_ids, caps, reserved,
                    cfg["calibration"], cfg["splits"]["master_seed"])
        else:
            cal_pools = {role: {"rows": [], "pairs": []} for role in ("cal_fit", "cal_check")}
        validate_calibration_pools(cal_pools, calibration_queries, reserved, caps,
                                   cfg["calibration"], n)
        cal_pools = {role: {"rows": list(pool["rows"]),
                            "pairs": [(qid, int(row)) for qid, row in pool["pairs"]]}
                     for role, pool in cal_pools.items()}
        paid_accessor.register_calibration_pools(cal_pools)
        for role in ("cal_fit", "cal_check"):
            if cal_pools[role]["rows"]:
                paid_accessor.request(cal_pools[role]["rows"], role, bootstrap_cap)
        heldout = set(map(int, validation)) | set(cal_pools["cal_fit"]["rows"]) | set(cal_pools["cal_check"]["rows"])
        M0, fit_record = fit_global_map(cfg["mapping"]["kind"], (old_vectors[train], y_train),
                                       (old_vectors[validation], y_val), cfg["mapping"], map_seed)
        if cfg["mapping"]["regional"] == "none":
            regions = {"assignments": np.zeros(n, dtype=np.int64),
                       "centers": np.mean(old_vectors, axis=0, keepdims=True),
                       "sample_rows": np.arange(n, dtype=np.int64)}
        else:
            regions = fit_regions(old_vectors, len(train), map_seed)
        stats = RegionalStatistics(y_train.shape[1], len(regions["centers"]), cfg["mapping"]["ridge"])
        stats.add_pairs(train, transform_global(M0, old_vectors[train]), y_train,
                        regions["assignments"], excluded=heldout)
        regional = stats.fit(cfg["mapping"]["min_region_pairs"], cfg["mapping"]["regional"])
        stats.dirty.clear()
        vectors = map_documents(np.arange(n), old_vectors, M0, regional, regions["assignments"])
        paid_rows = np.array(sorted(paid_accessor.paid), dtype=np.int64)
        fidelity = np.zeros(n, dtype=bool)
        vectors[paid_rows] = np.stack([paid_accessor.cache[row] for row in paid_rows])
        fidelity[paid_rows] = True
        index_args = {"chunk_rows": cfg["search"]["chunk_rows"]}
        if cfg["search"]["backend"] == "hnsw":
            index_type = HnswIndex
            index_args.update({key: cfg["search"][key] for key in
                               ("candidates", "ef_search", "M", "ef_construction", "threads")})
            index_args["seed"] = map_seed
        else:
            index_type = ExactIndex
        index = index_type(vectors, doc_ids, fidelity, Calibration(), **index_args)
        needed_queries = {str(qid) for role in cal_pools.values() for qid, _ in role["pairs"]}
        query_vectors = {str(qid): vector for role in calibration_queries.values()
                         for qid, vector in role.items() if str(qid) in needed_queries}
        state = MigrationState(index, M0, regions, stats, regional, paid_accessor, old_vectors,
                               np.random.default_rng(traffic_seed), [], heldout, cfg,
                               max(1, math.ceil(cfg["scheduler"]["refit_fraction"] * n)), costs,
                               cal_pools, query_vectors)
        with cost_scope("calibration_fit_check", costs):
            calibration = refresh_calibration(state)
            index.commit_index_update([], np.empty((0, vectors.shape[1]), dtype=np.float32), [],
                                       cal=calibration)
    costs.append({"component": "map_fit", **fit_record})
    return state


def commit_backfill(state, selected, budget_limit=None):
    from .runtime import cost_scope
    selected = np.asarray(selected, dtype=np.int64)
    if not len(selected) or len(set(selected)) != len(selected) or state.index.fidelity[selected].any():
        raise ValueError("Backfill must contain unique mapped documents")
    with cost_scope("backfill_access_commit", state.cost_records):
        limit = len(state.index.ids) if budget_limit is None else budget_limit
        values = state.accessor.request(selected, "backfill", limit)
        state.index.commit_index_update(selected, values, True)
        state.statistics.add_pairs(selected, transform_global(state.M0, state.old_vectors[selected]),
                                   values, state.regions["assignments"], excluded=state.heldout)
        state.backfilled.extend(map(int, selected))


def maybe_refit_and_remap(state):
    from .runtime import cost_scope
    n = len(state.index.ids)
    interval = max(1, math.ceil(state.cfg["scheduler"]["refit_fraction"] * n))
    if len(state.backfilled) < state.next_refit:
        return []
    touched = sorted(state.statistics.dirty)
    remapped = np.empty(0, dtype=np.int64)
    if touched and state.cfg["mapping"]["regional"] != "none":
        with cost_scope("regional_solve_remap_commit", state.cost_records) as record:
            regional = state.statistics.fit(state.cfg["mapping"]["min_region_pairs"],
                                             state.cfg["mapping"]["regional"],
                                             regions=touched, current=state.regional)
            mask = ~state.index.fidelity & np.isin(state.regions["assignments"], touched)
            remapped = np.flatnonzero(mask)
            vectors = map_documents(remapped, state.old_vectors, state.M0, regional,
                                    state.regions["assignments"]) if len(remapped) else np.empty(
                                        (0, state.index.vectors.shape[1]), dtype=np.float32)
            calibration = refresh_calibration(state, regional)
            state.index.commit_index_update(remapped, vectors, False, cal=calibration)
            state.regional = regional
            record.update(remapped_count=len(remapped), vector_bytes=int(len(remapped) * state.index.vectors.shape[1] * 4))
    state.statistics.dirty.clear()
    state.next_refit += interval
    return remapped.tolist()


def emit_checkpoint(state, output, checkpoint_id, config_hash):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    destination = output / checkpoint_id
    if destination.exists():
        marker = read_json(destination / "checkpoint.json")
        if marker["config_hash"] != config_hash or marker["backfilled"] != len(state.backfilled):
            raise ValueError("Checkpoint path already contains a different prefix")
        return destination
    temp = Path(tempfile.mkdtemp(prefix=f".{checkpoint_id}-", dir=output))
    state.index.save_index(temp / "index")
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
    files = {str(p.relative_to(temp)): file_digest(p) for p in temp.rglob("*") if p.is_file()}
    marker = {"complete": True, "config_hash": config_hash,
              "next_refit": state.next_refit, "backfilled": len(state.backfilled),
              "paid": len(state.accessor.paid), "rng": state.rng.bit_generator.state,
              "cost_records": state.cost_records, "read_state": state.read_state,
              "accessor_cost": state.accessor.cost, "files": files}
    write_json(temp / "checkpoint.json", marker)
    temp.rename(destination)
    return destination


def restore_migration(checkpoint, old_vectors, accessor, cfg, config_hash):
    checkpoint = Path(checkpoint)
    record = read_json(checkpoint / "checkpoint.json")
    if not record.get("complete") or record["config_hash"] != config_hash:
        raise ValueError("Incomplete or incompatible migration checkpoint")
    for name, checksum in record["files"].items():
        if file_digest(checkpoint / name) != checksum:
            raise ValueError("Checkpoint file checksum mismatch")
    index = load_index(checkpoint / "index")
    cal_path = checkpoint / "calibration_pools.json"
    cal_pools = (read_json(cal_path) if cal_path.exists() else
                 {role: {"rows": [], "pairs": []} for role in ("cal_fit", "cal_check")})
    cal_pools = {role: {"rows": pool["rows"], "pairs": [(qid, int(row)) for qid, row in pool["pairs"]]}
                 for role, pool in cal_pools.items()}
    accessor.register_calibration_pools(cal_pools)
    queries = {}
    if (checkpoint / "calibration_queries.npz").exists():
        with np.load(checkpoint / "calibration_queries.npz", allow_pickle=False) as cal_arrays:
            queries = dict(zip(cal_arrays["query_ids"].tolist(), cal_arrays["vectors"]))
    with np.load(checkpoint / "state.npz", allow_pickle=False) as arrays:
        stats = RegionalStatistics(index.vectors.shape[1], len(arrays["centers"]), cfg["mapping"]["ridge"])
        stats.H, stats.B, stats.counts = arrays["H"], arrays["B"], arrays["counts"]
        stats.seen, stats.dirty = set(map(int, arrays["stats_seen"])), set(map(int, arrays["dirty"]))
        regions = {key: arrays[key] for key in ("centers", "assignments", "sample_rows")}
        order = arrays["paid_order"].tolist()
        if accessor.paid - set(order):
            raise ValueError("Access journal is ahead of checkpoint; reconcile pending access before resume")
        accessor.order, accessor.paid = order, set(order)
        accessor.cache = {row: index.vectors[row].copy() for row in order}
        if "accessor_cost" in record:
            accessor.cost = record["accessor_cost"]
        accessor._persist()
        rng = np.random.default_rng()
        rng.bit_generator.state = record["rng"]
        return MigrationState(index, load_map_state(checkpoint / "M0.safetensors"), regions,
                              stats, arrays["regional"], accessor, old_vectors, rng,
                              arrays["backfilled"].tolist(), set(map(int, arrays["heldout"])), cfg,
                              record["next_refit"], record["cost_records"], cal_pools, queries,
                              record.get("read_state", {"cursor": 0, "pending": []}))


def refresh_scheduling_snapshot(state, traffic):
    from .runtime import cost_scope
    if set(traffic.query_ids) & set(state.calibration_queries):
        raise PermissionError("Calibration queries cannot enter scheduling gain")
    candidates = {}
    with cost_scope("scheduling_full_refresh", state.cost_records) as record:
        for start in range(0, len(traffic.query_ids), 32):
            result = state.index.search(traffic.vectors[start:start + 32])
            proxies = traffic.proxies[start:start + 32] if traffic.proxies is not None else None
            local = build_candidate_sets(result, proxies, state.index.fidelity,
                                          state.index.calibration.radius,
                                          traffic.weights[start:start + 32])
            candidates.update({start + q: values for q, values in local.items()})
        record.update(queries_refreshed=len(traffic.query_ids), at_risk_queries=len(candidates),
                      proxy_policy="served_top10" if traffic.proxies is None else "scheduling_labels",
                      epoch=state.index.epoch)
    return candidates


def run_migration(state, targets, evaluator_callback=None, scheduling_refresh=None,
                   schedule_edges=(), traffic=None):
    n = len(state.index.ids)
    events, evaluations = [], []
    interval = max(1, math.ceil(state.cfg["scheduler"]["refit_fraction"] * n))
    if traffic is not None:
        previous = state.read_state.get("traffic_hash")
        if previous and previous != traffic.fingerprint:
            raise ValueError("Scheduling traffic changed across a migration prefix")
        state.read_state["traffic_hash"] = traffic.fingerprint
        if set(traffic.query_ids) & set(state.calibration_queries):
            raise PermissionError("Calibration queries cannot be scheduling traffic")
        if not schedule_edges and traffic.proxies is not None:
            schedule_edges = [(query, row) for query, rows in enumerate(traffic.proxies)
                               for row in (rows or ())]
    for target in targets:
        if target < len(state.accessor.paid):
            continue
        while len(state.accessor.paid) < target:
            cap = choose_batch_cap(n, len(state.accessor.paid), len(state.backfilled), target,
                                    interval, state.cfg["scheduler"]["batch_fraction"])
            if cap <= 0:
                raise RuntimeError("NO_PROGRESS: batch cap did not advance a boundary")
            mapped = ~state.index.fidelity
            kind = state.cfg["scheduler"]["kind"]
            metadata = {"greedy_count": 0, "fallback_count": 0}
            if kind == "random":
                selected = select_random(mapped, cap, state.rng)
            elif kind == "degree":
                selected = select_degree(schedule_edges, mapped, cap, state.index.ids)
            elif kind == "greedy":
                candidates = {}
                if state.index.calibration.radius is not None:
                    if scheduling_refresh is not None:
                        candidates = scheduling_refresh(state)
                    elif traffic is not None:
                        candidates = refresh_scheduling_snapshot(state, traffic)
                selected, metadata = select_greedy(candidates, cap, mapped, state.rng, state.index.ids)
                if state.index.calibration.radius is None:
                    metadata["reason"] = "radius_unavailable"
            elif kind == "read":
                if traffic is None:
                    raise ValueError("Re-embed-on-read requires fixed scheduling queries")
                selected, metadata = select_on_read(
                    range(len(traffic.query_ids)), lambda q: state.index.search(traffic.vectors[q:q + 1]),
                    cap, state.read_state, mapped, state.rng)
            else:
                raise NotImplementedError(f"Scheduler {kind} requires its primary implementation")
            commit_backfill(state, selected, budget_limit=target)
            remapped = maybe_refit_and_remap(state)
            events.append({"epoch": state.index.epoch, "paid": len(state.accessor.paid),
                           "backfilled": len(state.backfilled), "remapped_count": len(remapped),
                           "f_accessed": len(state.accessor.paid) / n,
                           "f_scheduled": len(state.backfilled) / n,
                           "f_true": float(state.index.fidelity.mean()), **metadata})
        if evaluator_callback:
            evaluations.append(evaluator_callback(state.index, target))
    return {"events": events, "evaluations": evaluations, "stop_reason": "TARGET_REACHED"}
