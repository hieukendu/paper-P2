"""E6 chronological AOL-IA replay on the real recovered query timeline.

The runner keeps the static migration primitives (paid accessor, frozen map,
calibration, same-ID updates and checkpoints) but changes the scheduler input
at each decision to the history available at that cutoff.  Future events are
used only by the evaluator after the decision has been committed.
"""

from copy import deepcopy
import gzip
import gc
import json
from pathlib import Path
import resource
import time

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from .config import load_tuning_profiles, redacted_config, validate_tuning_profile
from .data.prepare import validate_prepared
from .data.splits import sample_document_pools
from .encoders import model_specs, resolve_model
from .experiments import finalize_run, source_hash
from .experiments_e7 import (_case_vector_store, case_manifest_path, load_case_manifest,
                             _scale_parent)
from .hf_sync import snapshot_source
from .io import atomic_bytes, digest, read_json, write_json
from .migration import (bootstrap_migration, choose_batch_cap, commit_backfill,
                         emit_checkpoint, maybe_refit_and_remap,
                         refresh_scheduling_snapshot, restore_migration)
from .runtime import cost_scope, probe_hardware, require_target_hardware
from .scheduling import (SchedulingTraffic, select_degree, select_greedy,
                         select_on_read, select_random)
from .vectors import PaidEmbeddingAccessor, encode_query_pool


RUN_BUDGET_POLICY = "compact_v1"
SCALE_VARIANT = "e4e567_scale_v3_50k"
E6_MAP_SEED = 17
E6_TRAFFIC_SEED = 101
E6_WEEKS = 8
E6_DECISIONS = 7
E6_EVENT_CAP = 50_000
E6_SCHEDULED_FRACTION = 0.07


def _peak_rss_bytes():
    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024)


def _load_case_profile(cfg, root):
    profiles = load_tuning_profiles(Path(root) / cfg["tuning"]["lock_path"])
    profile_hash = cfg["experiment"].get("profile_hash")
    profile = profiles["profiles"].get(profile_hash)
    if profile is None or profile.get("scope") != cfg["experiment"].get("tuning_scope"):
        raise ValueError("E6_PROFILE_REQUIRED: AOL case-scoped profile is missing")
    validate_tuning_profile({
        "phase": "official", "profile_hash": profile_hash,
        "tuning_scope": profile["scope"], "input_refs": profile["inputs"],
        "variant_id": "primary", "overrides": {},
    }, cfg, profiles)
    return profile_hash, profile


def _load_temporal_events(prepared):
    table = pq.read_table(
        Path(prepared) / "temporal_events.parquet",
        columns=["event_id", "week", "timestamp", "user_cluster", "group_id",
                 "query_id", "query_text", "doc_row", "clicked"],
    )
    rows = table.to_pylist()
    if not rows:
        raise ValueError("E6_INPUT_GATE_FAILED: temporal event release is empty")
    weeks = {int(row["week"]) for row in rows}
    if weeks != set(range(E6_WEEKS)):
        raise ValueError("E6_INPUT_GATE_FAILED: chronology does not cover exactly eight weeks")
    if [int(row["event_id"]) for row in rows] != list(range(len(rows))):
        raise ValueError("E6_INPUT_GATE_FAILED: event IDs are not contiguous")
    timestamps = [str(row["timestamp"]) for row in rows]
    if timestamps != sorted(timestamps):
        raise ValueError("E6_INPUT_GATE_FAILED: events are not in chronological order")
    if any(sum(int(row["week"]) == week for row in rows) > E6_EVENT_CAP
           for week in range(E6_WEEKS)):
        raise ValueError("E6_INPUT_GATE_FAILED: weekly event cap exceeded")
    return rows


def _group_query_records(events):
    records = {}
    for event in events:
        current = records.setdefault(event["group_id"], {
            "text": event["query_text"], "query_ids": set(), "weeks": set()})
        if current["text"] != event["query_text"]:
            raise ValueError("E6_INPUT_GATE_FAILED: group text changed across events")
        current["query_ids"].add(event["query_id"])
        current["weeks"].add(int(event["week"]))
    ids = sorted(records)
    return ids, {group_id: records[group_id]["text"] for group_id in ids}, records


def _encode_temporal_queries(cfg, root, dataset_release, pair, group_ids, texts, spec, role, timing):
    path = (Path(cfg["paths"]["cache"]) / "e6" / "queries" /
            f"{pair}-{dataset_release[:16]}-{role}")
    started = time.monotonic()
    values, meta = encode_query_pool(group_ids, [texts[group_id] for group_id in group_ids],
                                     spec, cfg, path)
    timing.append({"component": f"encode_{role}_queries", "wall_seconds": time.monotonic() - started,
                   "source": "measured", "rows": len(group_ids),
                   "cache_hit": meta.get("cache_hit", False)})
    return np.asarray(values, dtype=np.float32), meta


def _gpu_top10(vectors, queries, fidelity=None, calibration=None, device="cuda"):
    """Exact top-10 in batches; GPU path avoids a Python loop over AOL events."""
    queries = np.asarray(queries, dtype=np.float32)
    if not len(queries):
        return np.empty((0, 10), dtype=np.int64)
    try:
        import torch
        use_gpu = device.startswith("cuda") and torch.cuda.is_available()
    except ImportError:
        use_gpu = False
    if not use_gpu:
        from .index import ExactIndex
        ids = [str(row) for row in range(len(vectors))]
        return ExactIndex(vectors, ids, fidelity, calibration).search(queries).rows[:, :10]
    import torch
    matrix = torch.as_tensor(np.asarray(vectors, dtype=np.float32), device=device)
    query_tensor = torch.as_tensor(queries, device=device)
    fidelity_tensor = (None if fidelity is None else
                       torch.as_tensor(np.asarray(fidelity, dtype=bool), device=device))
    output = []
    batch = 512
    k = min(10, matrix.shape[0])
    for start in range(0, len(query_tensor), batch):
        scores = query_tensor[start:start + batch] @ matrix.T
        if fidelity_tensor is not None and calibration is not None:
            scores = torch.where(fidelity_tensor[None, :], scores,
                                 calibration.a * scores + calibration.b)
        rows = torch.topk(scores, k=k, dim=1, largest=True, sorted=True).indices
        output.append(rows.cpu().numpy().astype(np.int64, copy=False))
    return np.concatenate(output, axis=0)


def _history_traffic(events, week, group_ids, group_vectors, calibration_groups):
    """Build scheduler traffic strictly from events at or before `week`."""
    wanted = set(group_ids)
    counts = {}
    proxies = {}
    for event in events:
        if int(event["week"]) > week or event["group_id"] not in wanted:
            continue
        group_id = event["group_id"]
        if group_id in calibration_groups:
            continue
        counts[group_id] = counts.get(group_id, 0.0) + 1.0
        if int(event["doc_row"]) >= 0:
            proxies.setdefault(group_id, set()).add(int(event["doc_row"]))
        else:
            proxies.setdefault(group_id, set())
    ids = sorted(counts)
    if not ids:
        return None, [], {"history_groups": 0, "history_events": 0,
                          "future_groups_in_scheduler": 0}
    traffic = SchedulingTraffic(
        tuple(ids), np.stack([group_vectors[group_id] for group_id in ids]),
        [proxies.get(group_id, set()) for group_id in ids],
        np.asarray([counts[group_id] for group_id in ids], dtype=np.float64),
    )
    edges = [(index, row) for index, group_id in enumerate(ids)
             for row in sorted(proxies.get(group_id, set()))]
    return traffic, edges, {
        "history_groups": len(ids), "history_events": int(sum(counts.values())),
        "future_groups_in_scheduler": 0,
    }


def _temporal_step(state, target, traffic, edges, cfg):
    """Advance one cutoff using the same selectors and paid-access ledger."""
    n = len(state.index.ids)
    events = []
    interval = max(1, int(np.ceil(cfg["scheduler"]["refit_fraction"] * n)))
    while len(state.accessor.paid) < target:
        cap = choose_batch_cap(n, len(state.accessor.paid), len(state.backfilled), target,
                               interval, cfg["scheduler"]["batch_fraction"])
        if cap <= 0:
            raise RuntimeError("E6_NO_PROGRESS: temporal batch did not advance")
        mapped = ~state.index.fidelity
        kind = cfg["scheduler"]["kind"]
        metadata = {"greedy_count": 0, "fallback_count": 0}
        if kind == "random":
            selected = select_random(mapped, cap, state.rng)
        elif kind == "degree":
            selected = select_degree(edges, mapped, cap, state.index.ids)
        elif kind == "greedy":
            candidates = refresh_scheduling_snapshot(state, traffic) if traffic is not None else {}
            selected, metadata = select_greedy(candidates, cap, mapped, state.rng, state.index.ids)
        elif kind == "read":
            if traffic is None:
                raise ValueError("E6_READ_REQUIRES_HISTORY: no prior query history")
            selected, metadata = select_on_read(
                range(len(traffic.query_ids)),
                lambda query: state.index.search(traffic.vectors[query:query + 1]),
                cap, state.read_state, mapped, state.rng,
            )
        else:
            raise ValueError(f"E6_SCHEDULER_INVALID: {kind}")
        commit_backfill(state, selected, budget_limit=target)
        remapped = maybe_refit_and_remap(state)
        events.append({"paid": len(state.accessor.paid), "backfilled": len(state.backfilled),
                       "remapped_count": len(remapped),
                       "f_accessed": len(state.accessor.paid) / n,
                       "f_scheduled": len(state.backfilled) / n,
                       "f_true": float(state.index.fidelity.mean()), **metadata})
    return events


def _evaluate_week(state, target_vectors, group_ids, group_vectors, group_weights, doc_ids,
                   week, retrieval):
    query_matrix = np.stack([group_vectors[group_id] for group_id in group_ids])
    full_rows = _gpu_top10(target_vectors, query_matrix, device=state.cfg["execution"]["device"])
    current_rows = _gpu_top10(
        state.index.vectors, query_matrix, state.index.fidelity, state.index.calibration,
        state.cfg["execution"]["device"],
    )
    records = []
    for index, group_id in enumerate(group_ids):
        overlap = len(set(current_rows[index]) & set(full_rows[index])) / 10.0
        weight = float(group_weights[group_id])
        records.append({"week": week, "group_id": group_id, "weight": weight,
                        "arr_at_10": overlap,
                        "current_top1": doc_ids[int(current_rows[index, 0])],
                        "full_new_top1": doc_ids[int(full_rows[index, 0])]})
        for rank, row in enumerate(current_rows[index], 1):
            retrieval.write(f"{group_id} Q0 {doc_ids[int(row)]} {rank} {-rank} e6-week-{week}-current\n")
        for rank, row in enumerate(full_rows[index], 1):
            retrieval.write(f"{group_id} Q0 {doc_ids[int(row)]} {rank} {-rank} e6-week-{week}-full-new\n")
    denominator = sum(row["weight"] for row in records)
    weighted_arr = (sum(row["weight"] * row["arr_at_10"] for row in records) /
                    denominator if denominator else 0.0)
    return records, {"week": week, "groups": len(records), "events": int(denominator),
                     "weighted_arr_at_10": float(weighted_arr),
                     "scheduled_fraction": len(state.backfilled) / len(state.index.ids),
                     "accessed_fraction": len(state.accessor.paid) / len(state.index.ids),
                     "true_fraction": float(state.index.fidelity.mean())}


def _user_block_bootstrap(events, metric_rows, week, draws, seed):
    """Bootstrap the weighted ARR using user blocks, without emitting user IDs."""
    arr_by_group = {
        row["group_id"]: float(row["arr_at_10"])
        for row in metric_rows if int(row["week"]) == week
    }
    blocks = {}
    for event in events:
        if int(event["week"]) != week or event["group_id"] not in arr_by_group:
            continue
        block = blocks.setdefault(event["user_cluster"], [0.0, 0])
        block[0] += arr_by_group[event["group_id"]]
        block[1] += 1
    numerators = np.asarray([value[0] for value in blocks.values()], dtype=np.float64)
    denominators = np.asarray([value[1] for value in blocks.values()], dtype=np.float64)
    total = float(denominators.sum())
    estimate = float(numerators.sum() / total) if total else 0.0
    draws = int(draws)
    if len(numerators) < 2 or draws < 1:
        return {"method": "user_block_bootstrap_v1", "blocks": len(numerators),
                "draws": 0, "estimate": estimate, "ci95_low": estimate,
                "ci95_high": estimate, "status": "INSUFFICIENT_BLOCKS"}
    rng = np.random.default_rng(seed)
    samples = np.empty(draws, dtype=np.float64)
    block_count = len(numerators)
    for start in range(0, draws, 256):
        stop = min(draws, start + 256)
        indices = rng.integers(0, block_count, size=(stop - start, block_count))
        sample_denominator = denominators[indices].sum(axis=1)
        samples[start:stop] = (numerators[indices].sum(axis=1) /
                                np.maximum(sample_denominator, 1.0))
    low, high = np.quantile(samples, [0.025, 0.975])
    return {"method": "user_block_bootstrap_v1", "blocks": block_count, "draws": draws,
            "estimate": estimate, "ci95_low": float(low), "ci95_high": float(high),
            "status": "PASS"}


def _day_sensitivity(events, metric_rows, week):
    """Report leave-one-day-out sensitivity for the weighted ARR endpoint."""
    arr_by_group = {
        row["group_id"]: float(row["arr_at_10"])
        for row in metric_rows if int(row["week"]) == week
    }
    days = {}
    for event in events:
        if int(event["week"]) != week or event["group_id"] not in arr_by_group:
            continue
        day = str(event["timestamp"]).split(" ", 1)[0]
        value = days.setdefault(day, [0.0, 0])
        value[0] += arr_by_group[event["group_id"]]
        value[1] += 1
    total_numerator = sum(value[0] for value in days.values())
    total_denominator = sum(value[1] for value in days.values())
    estimate = (total_numerator / total_denominator) if total_denominator else 0.0
    daily = [value[0] / value[1] for value in days.values() if value[1]]
    leave_out = [
        (total_numerator - value[0]) / (total_denominator - value[1])
        for value in days.values() if total_denominator > value[1]
    ]
    if len(days) < 2 or not leave_out:
        return {"method": "leave_one_day_out_v1", "days": len(days),
                "estimate": float(estimate), "daily_min": float(min(daily)) if daily else 0.0,
                "daily_max": float(max(daily)) if daily else 0.0,
                "leave_one_day_out_min": float(estimate),
                "leave_one_day_out_max": float(estimate),
                "status": "INSUFFICIENT_DAYS"}
    return {"method": "leave_one_day_out_v1", "days": len(days),
            "estimate": float(estimate), "daily_min": float(min(daily)),
            "daily_max": float(max(daily)),
            "leave_one_day_out_min": float(min(leave_out)),
            "leave_one_day_out_max": float(max(leave_out)), "status": "PASS"}


def run_e6_cell(cfg, root):
    root = Path(root)
    if cfg["execution"]["phase"] != "official" or cfg["execution"]["mode"] != "cached_access":
        raise ValueError("E6 cells require official/cached_access")
    require_target_hardware(cfg, probe_hardware())
    if cfg["dataset"]["name"] != "aol-ia" or cfg["models"]["pair"] != "arctic":
        raise ValueError("E6_CELL_INVALID: AOL-IA with Arctic is the declared case")
    if cfg["experiment"]["map_seed"] != E6_MAP_SEED or cfg["experiment"]["traffic_seed"] != E6_TRAFFIC_SEED:
        raise ValueError("E6_CELL_INVALID: seed is outside the declared chronology")
    case_manifest, base_rows, manifest_file = load_case_manifest(cfg, root)
    profile_hash, profile = _load_case_profile(cfg, root)
    parent_info = _scale_parent(cfg, root)
    if profile["inputs"].get("case_manifest_hash") != case_manifest["manifest_hash"]:
        raise ValueError("E6_PROFILE_REQUIRED: profile and temporal case manifest differ")
    prepared = root / cfg["paths"]["data"] / "processed" / "aol-ia"
    data_manifest = validate_prepared(prepared)
    if data_manifest["temporal_policy"].get("future_leakage") != "forbidden":
        raise ValueError("E6_INPUT_GATE_FAILED: temporal policy is not pinned")
    events = _load_temporal_events(prepared)
    group_ids, group_text, group_records = _group_query_records(events)
    specs = {role: resolve_model(spec, cfg["paths"], root)
             for role, spec in model_specs("arctic", root).items()}
    runtime = profile["selections"]["runtime"]
    cfg = deepcopy(cfg)
    cfg["models"]["batch_size"] = int(runtime["batches"]["new"])
    cfg["search"]["threads"] = int(runtime["threads"]["selected_threads"])
    environment = probe_hardware()
    locked = {
        "config": redacted_config(cfg), "source_hash": source_hash(root),
        "run_budget_policy": RUN_BUDGET_POLICY, "scale_variant": SCALE_VARIANT,
        "dataset": "aol-ia", "model_pair": "arctic", "case_manifest_hash": case_manifest["manifest_hash"],
        "case_manifest_path": str(manifest_file.relative_to(root)),
        "temporal_release_hash": data_manifest["release_hash"],
        "profile_hash": profile_hash,
        "common_scale_manifest_hash": parent_info["manifest"]["manifest_hash"],
        "parent_e4_artifact_id": parent_info["parent"]["artifact_id"],
        "parent_e4_artifact_hash": parent_info["parent"]["artifact_hash"],
        "map_seed": E6_MAP_SEED, "traffic_seed": E6_TRAFFIC_SEED,
        "scheduler": cfg["scheduler"]["kind"], "claim_scope": "reduced_scale_pilot",
    }
    run_id = (f"E6-aol-ia-arctic-{cfg['scheduler']['kind']}-m{E6_MAP_SEED}-t{E6_TRAFFIC_SEED}-"
              f"{digest(locked)[:12]}")
    run_dir = Path(cfg["paths"]["runs"]) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    if (run_dir / "summary.json").exists():
        previous = read_json(run_dir / "summary.json")
        if previous.get("compute_status") == "COMPUTE_DONE":
            return finalize_run(run_dir, previous, cfg, root)
        raise ValueError("Failed E6 cell is preserved; enqueue a new immutable source revision")
    write_json(run_dir / "config.lock.json", locked)
    write_json(run_dir / "environment.json", environment)
    write_json(run_dir / "dataset_manifest.json", data_manifest)
    write_json(run_dir / "case_manifest.json", case_manifest)
    write_json(run_dir / "tuning_profile.json", {"profile_hash": profile_hash, **profile})
    write_json(run_dir / "temporal_manifest.json", {
        "release_hash": data_manifest["release_hash"],
        "case_manifest_hash": case_manifest["manifest_hash"],
        "weeks": E6_WEEKS, "decisions": E6_DECISIONS,
        "event_cap": E6_EVENT_CAP, "future_leakage": "forbidden",
        "quality_labels_opened": True,
    })
    write_json(run_dir / "models.lock.json", {
        role: {key: value for key, value in spec.items() if key != "snapshot"}
        for role, spec in specs.items()})
    snapshot_source(root, run_dir)
    summary = {
        "compute_status": "FAILED", "phase": "official", "outcome": "inconclusive",
        "expect_classification": "KHỚP", "correctness_gate": "FAIL",
        "quality_gate": "UNMEASURED", "performance_claim": False,
        "run_budget_policy": RUN_BUDGET_POLICY, "scale_variant": SCALE_VARIANT,
        "claim_scope": "reduced_scale_pilot", "scheduler": cfg["scheduler"]["kind"],
        "map_seed": E6_MAP_SEED, "traffic_seed": E6_TRAFFIC_SEED,
        "case_manifest_hash": case_manifest["manifest_hash"],
        "temporal_release_hash": data_manifest["release_hash"],
        "common_scale_manifest_hash": parent_info["manifest"]["manifest_hash"],
        "parent_e4_artifact_id": parent_info["parent"]["artifact_id"],
        "parent_e4_artifact_hash": parent_info["parent"]["artifact_hash"],
        "official_doc_pool": len(base_rows), "weekly_event_cap": E6_EVENT_CAP,
    }
    timing, step_events, metric_rows = [], [], []
    started = time.monotonic()
    new_store = old_store = None
    try:
        doc_ids_all = (prepared / "doc_ids.txt").read_text().splitlines()
        doc_ids = [doc_ids_all[int(row)] for row in base_rows]
        old_store, old_meta = _case_vector_store(
            prepared, base_rows, case_manifest, specs["old"], cfg, root, "old", timing)
        new_store, new_meta = _case_vector_store(
            prepared, base_rows, case_manifest, specs["new"], cfg, root, "new", timing)
        old = old_store.get_rows(np.arange(len(base_rows), dtype=np.int64))
        target = new_store.get_rows(np.arange(len(base_rows), dtype=np.int64))
        new_query_values, query_meta = _encode_temporal_queries(
            cfg, root, data_manifest["release_hash"], "arctic", group_ids, group_text,
            specs["new"], "all-groups-new", timing)
        group_vectors = dict(zip(group_ids, new_query_values))
        pools = sample_document_pools(doc_ids, cfg)
        pools["cal_cap"] = min(250, int(pools["cal_cap"]))
        if not len(pools["train"]) or not len(pools["validation"]):
            raise ValueError("E6_INPUT_GATE_FAILED: insufficient document bootstrap pools")
        cal_roles = read_json(prepared / "splits/query_roles.json")["roles"]
        cal_queries = {
            role: {group_id: group_vectors[group_id]
                   for group_id in cal_roles.get(role, []) if group_id in group_vectors}
            for role in ("cal_fit", "cal_check")}
        accessor = PaidEmbeddingAccessor(
            lambda requested: new_store.get_rows(requested),
            {"train": pools["train"], "validation": pools["validation"],
             "backfill": set(range(len(doc_ids))) - set(pools["train"]) - set(pools["validation"])},
            len(doc_ids), mode="cached_access", journal=run_dir / "access-journal.json")
        candidate = deepcopy(cfg)
        candidate["search"]["backend"] = "exact"
        with cost_scope("e6_bootstrap", timing):
            state = bootstrap_migration(doc_ids, pools, old, accessor, candidate,
                                        map_seed=E6_MAP_SEED, traffic_seed=E6_TRAFFIC_SEED,
                                        calibration_queries=cal_queries)
        group_weights_by_week = {week: {} for week in range(1, E6_WEEKS)}
        for event in events:
            week = int(event["week"])
            if 1 <= week < E6_WEEKS:
                group_weights_by_week[week][event["group_id"]] = (
                    group_weights_by_week[week].get(event["group_id"], 0.0) + 1.0)
        calibration_groups = set(cal_queries["cal_fit"]) | set(cal_queries["cal_check"])
        with gzip.open(run_dir / "retrieval.trec.gz", "wt") as retrieval:
            for decision in range(E6_DECISIONS):
                history_week = decision
                traffic, edges, history_meta = _history_traffic(
                    events, history_week, group_ids, group_vectors, calibration_groups)
                total_target = len(accessor.paid) + int(np.ceil(
                    (E6_SCHEDULED_FRACTION * len(doc_ids) - len(accessor.paid)) *
                    (decision + 1) / E6_DECISIONS))
                total_target = min(len(doc_ids), max(len(accessor.paid), total_target))
                step = _temporal_step(state, total_target, traffic, edges, candidate)
                step_events.extend({"decision": decision + 1, "history_week": history_week,
                                    "history_cutoff_exclusive_week": history_week + 1,
                                    "future_leakage": "PASS", **event} for event in step)
                future_week = decision + 1
                future_groups = sorted(group_weights_by_week[future_week])
                if not future_groups:
                    raise ValueError("E6_TEMPORAL_GATE_FAILED: future week has no evaluation groups")
                rows, weekly = _evaluate_week(
                    state, target, future_groups, group_vectors,
                    group_weights_by_week[future_week], doc_ids, future_week, retrieval)
                metric_rows.extend(rows)
                weekly.update({"decision": decision + 1, **history_meta,
                               "future_leakage": "PASS"})
                write_json(run_dir / "checkpoints" / f"week-{future_week:02d}.json", weekly)
                emit_checkpoint(state, run_dir / "checkpoints",
                                f"week-{future_week:02d}-state", digest(locked))
        restore_path = run_dir / "checkpoints" / "week-04-state"
        restore_accessor = PaidEmbeddingAccessor(
            lambda requested: new_store.get_rows(requested), accessor.roles, len(doc_ids),
            mode="cached_access")
        restored = restore_migration(restore_path, old, restore_accessor, candidate, digest(locked))
        checkpoint_index = read_json(restore_path / "index/index.json")
        checkpoint_fidelity = np.load(restore_path / "index/fidelity.npy", allow_pickle=False)
        with np.load(restore_path / "state.npz", allow_pickle=False) as checkpoint_state:
            checkpoint_backfilled = checkpoint_state["backfilled"].tolist()
            checkpoint_paid_order = checkpoint_state["paid_order"].tolist()
        if (restored.index.epoch != checkpoint_index["epoch"] or
                restored.backfilled != checkpoint_backfilled or
                restored.accessor.order != checkpoint_paid_order or
                not np.array_equal(restored.index.fidelity, checkpoint_fidelity)):
            raise ValueError("E6_CHECKPOINT_RESTORE_FAILED: restored state differs")
        pq.write_table(pa.Table.from_pylist(metric_rows), run_dir / "metrics.parquet")
        atomic_bytes(run_dir / "events.jsonl", "".join(
            json.dumps(event, sort_keys=True) + "\n" for event in step_events).encode())
        weekly = []
        for week in range(1, E6_WEEKS):
            rows = [row for row in metric_rows if row["week"] == week]
            weight = sum(row["weight"] for row in rows)
            weekly.append({"week": week, "groups": len(rows), "events": int(weight),
                           "weighted_arr_at_10": float(sum(row["weight"] * row["arr_at_10"]
                                                           for row in rows) / weight)})
        primary_week = E6_WEEKS - 1
        primary_weekly = next(row for row in weekly if row["week"] == primary_week)
        user_bootstrap = _user_block_bootstrap(
            events, metric_rows, primary_week, cfg["evaluation"]["bootstrap_draws"],
            E6_TRAFFIC_SEED + 1000,
        )
        day_sensitivity = _day_sensitivity(events, metric_rows, primary_week)
        write_json(run_dir / "e6_metrics.json", {
            "dataset": "aol-ia", "model_pair": "arctic", "scheduler": cfg["scheduler"]["kind"],
            "map_seed": E6_MAP_SEED, "traffic_seed": E6_TRAFFIC_SEED,
            "case_manifest_hash": case_manifest["manifest_hash"],
            "temporal_release_hash": data_manifest["release_hash"],
            "weekly": weekly, "decisions": E6_DECISIONS,
            "event_cap": E6_EVENT_CAP, "scheduled_fraction_cap": E6_SCHEDULED_FRACTION,
            "future_leakage": "PASS", "checkpoint_restore": "PASS",
            "primary_week": primary_week,
            "primary_week_weighted_arr_at_10": primary_weekly["weighted_arr_at_10"],
            "user_block_bootstrap": user_bootstrap,
            "day_sensitivity": day_sensitivity,
            "quality_labels_opened": True, "performance_claim": False,
        })
        write_json(run_dir / "timing.json", {
            "records": timing, "migration": state.cost_records,
            "accessor": state.accessor.cost, "old_cache": old_meta, "new_cache": new_meta,
            "query_cache": query_meta, "peak_rss_bytes": _peak_rss_bytes(),
            "wall_seconds": time.monotonic() - started, "performance_claim": False,
        })
        np.savez(run_dir / "accessed_ids.npz", paid=np.asarray(state.accessor.order),
                 backfilled=np.asarray(state.backfilled), train=pools["train"],
                 validation=pools["validation"])
        summary.update(compute_status="COMPUTE_DONE", correctness_gate="PASS",
                       quality_gate="MEASURED", temporal_gate="PASS",
                       checkpoint_restore="PASS", decisions=E6_DECISIONS,
                       documents=len(doc_ids), total_events=len(events),
                       final_accessed_fraction=len(state.accessor.paid) / len(doc_ids),
                       final_scheduled_fraction=len(state.backfilled) / len(doc_ids),
                       primary_week=primary_week,
                       primary_week_weighted_arr_at_10=primary_weekly["weighted_arr_at_10"],
                       user_block_bootstrap=user_bootstrap, day_sensitivity=day_sensitivity,
                       weekly=weekly, wall_seconds=time.monotonic() - started,
                       target_hardware_pass=True, performance_claim=False)
    except Exception as exc:
        summary.update(error_type=type(exc).__name__, reason=str(exc), correctness_gate="FAIL")
        write_json(run_dir / "timing.json", {"records": timing, "performance_claim": False})
    finally:
        gc.collect()
    return finalize_run(run_dir, summary, cfg, root)


def build_e6_tasks(cfg, root):
    """Build the serial four-cell E6 chronology after the AOL case profile."""
    root = Path(root)
    if cfg["experiment"].get("run_budget_policy") != RUN_BUDGET_POLICY:
        raise ValueError("E6 runner requires run_budget_policy=compact_v1")
    dataset, pair = "aol-ia", "arctic"
    scope = "case.aol-ia.arctic"
    profiles = load_tuning_profiles(root / cfg["tuning"]["lock_path"])
    matches = [(key, value) for key, value in profiles["profiles"].items()
               if value.get("scope") == scope]
    if len(matches) != 1:
        raise ValueError("E6_PROFILE_REQUIRED: exactly one AOL case profile is required")
    profile_hash, profile = matches[0]
    manifest_file = case_manifest_path(root, dataset, pair)
    manifest = read_json(manifest_file)
    parent = _scale_parent(cfg, root)
    common = {
        "config": "configs/experiments/e6.yaml", "phase": "official",
        "experiment": "E6", "measurement_mode": "quality", "priority": 30,
        "profile_hash": profile_hash, "tuning_scope": scope,
        "input_refs": profile["inputs"], "case_scope": scope,
        "parent_e4_artifact_id": parent["parent"]["artifact_id"],
        "parent_e4_artifact_hash": parent["parent"]["artifact_hash"],
        "resources": {"gpu_device": 0, "gpu_memory_gib": 24, "host_ram_gib": 32,
                       "cpu_cores": 8, "disk_scratch_gib": 20, "io_heavy": False},
    }
    tasks = []
    previous = None
    for scheduler in ("random", "degree", "read", "greedy"):
        task_id = f"E6.aol-ia.arctic.{scheduler}.m{E6_MAP_SEED}.t{E6_TRAFFIC_SEED}.{digest({'profile': profile_hash, 'scheduler': scheduler})[:12]}"
        overrides = {
            "execution": {"phase": "official", "mode": "cached_access"},
            "dataset": {"name": dataset, "subset_size": None},
            "models": {"pair": pair}, "scheduler": {"kind": scheduler},
            "mapping": {"kind": "residual_mlp"},
            "search": {"backend": "exact"},
            "experiment": {
                "profile_hash": profile_hash, "tuning_scope": scope,
                "run_budget_policy": RUN_BUDGET_POLICY, "cell_role": "required",
                "map_seed": E6_MAP_SEED, "traffic_seed": E6_TRAFFIC_SEED,
                "scale_variant": SCALE_VARIANT,
                "scale_manifest_hash": parent["manifest"]["manifest_hash"],
                "scale_manifest_path": str(Path(parent["manifest"]["path"]).relative_to(root)),
                "case_manifest_hash": manifest["manifest_hash"],
                "case_manifest_path": str(manifest_file.relative_to(root)),
                "case_scope": scope,
            },
        }
        task = {**common, "task_id": task_id, "config_overrides": overrides,
                "depends_on": [previous] if previous else [],
                "variant_id": "primary", "overrides": {}}
        tasks.append(task)
        previous = task_id
    from .queue import validate_jobs
    return validate_jobs(tasks)
