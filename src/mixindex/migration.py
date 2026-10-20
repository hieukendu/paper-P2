"""Shared bootstrap/backfill loop with complete, verifiable restart checkpoints."""

from dataclasses import dataclass
import math
from pathlib import Path
import tempfile

import numpy as np

from .calibration import Calibration
from .index import ExactIndex, HnswIndex, load_index
from .io import file_digest, read_json, write_json
from .maps import (RegionalStatistics, fit_global_map, fit_regions, load_map_state,
                   map_documents, save_map_state, transform_global)
from .scheduling import choose_batch_cap, select_degree, select_greedy, select_random


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


def bootstrap_migration(doc_ids, pools, old_vectors, paid_accessor, cfg, map_seed=17, traffic_seed=101):
    from .runtime import cost_scope
    costs = []
    with cost_scope("bootstrap", costs):
        n = len(doc_ids)
        train, validation = pools["train"], pools["validation"]
        y_train = paid_accessor.request(train, "train", n)
        y_val = paid_accessor.request(validation, "validation", n)
        M0, fit_record = fit_global_map(cfg["mapping"]["kind"], (old_vectors[train], y_train),
                                       (old_vectors[validation], y_val), cfg["mapping"], map_seed)
        if cfg["mapping"]["regional"] == "none":
            regions = {"assignments": np.zeros(n, dtype=np.int64),
                       "centers": np.mean(old_vectors, axis=0, keepdims=True),
                       "sample_rows": np.arange(n, dtype=np.int64)}
        else:
            regions = fit_regions(old_vectors, len(train), map_seed)
        stats = RegionalStatistics(y_train.shape[1], len(regions["centers"]), cfg["mapping"]["ridge"])
        stats.add_pairs(train, transform_global(M0, old_vectors[train]), y_train, regions["assignments"], excluded=validation)
        regional = stats.fit(cfg["mapping"]["min_region_pairs"], cfg["mapping"]["regional"])
        stats.dirty.clear()
        vectors = map_documents(np.arange(n), old_vectors, M0, regional, regions["assignments"])
        paid_rows = np.array(sorted(paid_accessor.paid), dtype=np.int64)
        fidelity = np.zeros(n, dtype=bool)
        vectors[paid_rows] = np.stack([paid_accessor.cache[row] for row in paid_rows])
        fidelity[paid_rows] = True
        # E1 has no calibration; primary calibration must be constructed from fixed role pools.
        if cfg["calibration"]["enabled"]:
            raise NotImplementedError("Fixed OP calibration proposals must be finalized before primary bootstrap")
        index_args = {"chunk_rows": cfg["search"]["chunk_rows"]}
        if cfg["search"]["backend"] == "hnsw":
            index_type = HnswIndex
            index_args.update({key: cfg["search"][key] for key in
                               ("candidates", "ef_search", "M", "ef_construction", "threads")})
            index_args["seed"] = map_seed
        else:
            index_type = ExactIndex
        index = index_type(vectors, doc_ids, fidelity, Calibration(), **index_args)
    costs.append({"component": "map_fit", **fit_record})
    return MigrationState(index, M0, regions, stats, regional, paid_accessor, old_vectors,
                          np.random.default_rng(traffic_seed), [], set(map(int, validation)), cfg,
                          max(1, math.ceil(cfg["scheduler"]["refit_fraction"] * n)), costs)


def commit_backfill(state, selected):
    from .runtime import cost_scope
    selected = np.asarray(selected, dtype=np.int64)
    if not len(selected) or len(set(selected)) != len(selected) or state.index.fidelity[selected].any():
        raise ValueError("Backfill must contain unique mapped documents")
    with cost_scope("backfill_access_commit", state.cost_records):
        values = state.accessor.request(selected, "backfill", len(state.index.ids))
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
            regional = state.statistics.fit(state.cfg["mapping"]["min_region_pairs"], state.cfg["mapping"]["regional"])
            mask = ~state.index.fidelity & np.isin(state.regions["assignments"], touched)
            remapped = np.flatnonzero(mask)
            if len(remapped):
                vectors = map_documents(remapped, state.old_vectors, state.M0, regional,
                                        state.regions["assignments"])
                state.index.commit_index_update(remapped, vectors, False)
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
    files = {str(p.relative_to(temp)): file_digest(p) for p in temp.rglob("*") if p.is_file()}
    marker = {"complete": True, "config_hash": config_hash,
              "next_refit": state.next_refit, "backfilled": len(state.backfilled),
              "paid": len(state.accessor.paid), "rng": state.rng.bit_generator.state,
              "cost_records": state.cost_records, "files": files}
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
        accessor._persist()
        rng = np.random.default_rng()
        rng.bit_generator.state = record["rng"]
        return MigrationState(index, load_map_state(checkpoint / "M0.safetensors"), regions,
                              stats, arrays["regional"], accessor, old_vectors, rng,
                              arrays["backfilled"].tolist(), set(map(int, arrays["heldout"])), cfg,
                              record["next_refit"], record["cost_records"])


def run_migration(state, targets, evaluator_callback=None, scheduling_refresh=None, schedule_edges=()):
    n = len(state.index.ids)
    events, evaluations = [], []
    interval = max(1, math.ceil(state.cfg["scheduler"]["refit_fraction"] * n))
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
                candidates = scheduling_refresh(state) if scheduling_refresh and state.index.calibration.radius is not None else {}
                selected, metadata = select_greedy(candidates, cap, mapped, state.rng, state.index.ids)
            else:
                raise NotImplementedError(f"Scheduler {kind} requires its primary implementation")
            commit_backfill(state, selected)
            remapped = maybe_refit_and_remap(state)
            events.append({"epoch": state.index.epoch, "paid": len(state.accessor.paid),
                           "backfilled": len(state.backfilled), "remapped_count": len(remapped),
                           "f_accessed": len(state.accessor.paid) / n,
                           "f_scheduled": len(state.backfilled) / n,
                           "f_true": float(state.index.fidelity.mean()), **metadata})
        if evaluator_callback:
            evaluations.append(evaluator_callback(state.index, target))
    return {"events": events, "evaluations": evaluations, "stop_reason": "TARGET_REACHED"}
