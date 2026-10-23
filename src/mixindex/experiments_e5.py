"""E5 reduced-scale static scheduler comparison.

The runner deliberately uses the same migration primitives as E2/E4.  The
common 50k/5k manifest, frozen scale profile and verified E4 full-bootstrap
artifact are admission gates; the four scheduler cells only differ in the
declared scheduler and map/traffic seeds.
"""

from copy import deepcopy
import json
from pathlib import Path
import resource
import time

import numpy as np
import pyarrow.parquet as pq

from .calibration import make_calibration_proposal, validate_calibration_pools
from .config import load_tuning_profiles, redacted_config
from .data.splits import sample_document_pools
from .experiments import finalize_run, source_hash
from .experiments_e4 import _artifact_hash, _encode_full_vectors, _profile_context
from .experiments_scale import _encode_queries, _traffic_proxies
from .hf_sync import snapshot_source
from .index import ExactIndex
from .io import atomic_bytes, digest, read_json, write_json
from .migration import (bootstrap_migration, emit_checkpoint, restore_migration,
                        run_migration)
from .maps import fit_op
from .progress import update_checklist
from .runtime import probe_hardware, require_target_hardware
from .scale_manifest import DOCUMENT_CAP, ORCAS_GROUP_CAP, SCALE_VARIANT
from .scheduling import SchedulingTraffic
from .vectors import PaidEmbeddingAccessor


RUN_BUDGET_POLICY = "compact_v1"
E5_SCHEDULERS = ("random", "degree", "read", "greedy")
E5_MAP_SEEDS = (17, 29, 43)
E5_TRAFFIC_SEED = 101


def _peak_rss_bytes():
    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024)


def _scale_pipeline_hash(cfg, context):
    """Hash settings shared by every E5 cell, excluding cell seeds/scheduler."""
    return digest({
        "scale_variant": context["scale_variant"],
        "common_scale_manifest_hash": context["scale_manifest"]["manifest_hash"],
        "profile_hash": context["profile_hash"],
        "dataset": context["docs_manifest"]["release_hash"],
        "orcas": context["orcas_manifest"]["release_hash"],
        "models": cfg["models"],
        "mapping": {key: value for key, value in cfg["mapping"].items()
                    if key not in {"kind", "lr"}},
        "calibration": cfg["calibration"],
        "search": cfg["search"],
        "scheduler_policy": {key: cfg["scheduler"][key]
                              for key in ("batch_fraction", "refit_fraction", "fallback")},
        "budget": cfg["budget"],
        "evaluation": {"primary_static_fraction": cfg["evaluation"]["primary_static_fraction"],
                        "map_seeds": list(E5_MAP_SEEDS),
                        "traffic_seed": E5_TRAFFIC_SEED},
    })


def _find_verified_e4_parent(cfg, root, context):
    state_path = Path(cfg["paths"]["state"]) / "tasks.json"
    if not state_path.exists():
        raise ValueError("E5_PARENT_REQUIRED: state/tasks.json is missing")
    state = read_json(state_path)
    matches = []
    for identifier, record in state.get("tasks", {}).items():
        spec = record.get("spec", {})
        override = spec.get("config_overrides", {}).get("experiment", {})
        if (spec.get("experiment") != "E4" or override.get("scale_task") != "full_bootstrap"
                or record.get("status") != "COMPUTE_DONE"
                or record.get("sync_status") != "VERIFIED"
                or record.get("handle_alive") is not False):
            continue
        run_value = record.get("run_dir")
        if not run_value:
            continue
        run_dir = Path(run_value)
        summary_path = run_dir / "summary.json"
        if not summary_path.exists():
            continue
        summary = read_json(summary_path)
        if (summary.get("scale_variant") != SCALE_VARIANT
                or summary.get("common_scale_manifest_hash") != context["scale_manifest"]["manifest_hash"]
                or summary.get("profile_hash") != context["profile_hash"]
                or summary.get("correctness_gate") != "PASS"
                or not summary.get("e4_artifact_hash")):
            continue
        actual_hash = _artifact_hash(run_dir)
        if actual_hash != summary["e4_artifact_hash"]:
            raise ValueError("E5_PARENT_INVALID: E4 artifact hash differs from summary")
        matches.append((identifier, record, summary, run_dir))
    if len(matches) != 1:
        raise ValueError("E5_PARENT_REQUIRED: exactly one verified v3 E4 full-bootstrap is required")
    identifier, record, summary, run_dir = matches[0]
    return {"task_id": identifier, "record": record, "summary": summary,
            "run_dir": run_dir, "artifact_id": run_dir.name,
            "artifact_hash": summary["e4_artifact_hash"]}


def _find_parent_release_attestation(cfg, root):
    """Find the already verified E4 release manifest without rehashing inputs."""
    state_path = Path(cfg["paths"]["state"]) / "tasks.json"
    if not state_path.exists():
        raise ValueError("E5_PARENT_REQUIRED: state/tasks.json is missing")
    state = read_json(state_path)
    matches = []
    for identifier, record in state.get("tasks", {}).items():
        spec = record.get("spec", {})
        override = spec.get("config_overrides", {}).get("experiment", {})
        if (spec.get("experiment") != "E4" or override.get("scale_task") != "full_bootstrap"
                or record.get("status") != "COMPUTE_DONE"
                or record.get("sync_status") != "VERIFIED"
                or record.get("handle_alive") is not False):
            continue
        run_value = record.get("run_dir")
        if not run_value:
            continue
        run_dir = Path(run_value)
        summary_path = run_dir / "summary.json"
        dataset_path = run_dir / "dataset_manifest.json"
        if not summary_path.exists() or not dataset_path.exists():
            continue
        summary = read_json(summary_path)
        if (summary.get("scale_variant") == SCALE_VARIANT
                and summary.get("common_scale_manifest_hash") == cfg["experiment"].get("scale_manifest_hash")
                and summary.get("profile_hash") == cfg["experiment"].get("profile_hash")
                and summary.get("correctness_gate") == "PASS"):
            matches.append((identifier, record, summary, run_dir, read_json(dataset_path)))
    if len(matches) != 1:
        raise ValueError("E5_PARENT_REQUIRED: exactly one verified v3 E4 release attestation is required")
    return matches[0]


def _find_verified_e4_tail(cfg, root, context):
    state_path = Path(cfg["paths"]["state"]) / "tasks.json"
    state = read_json(state_path)
    matches = []
    for identifier, record in state.get("tasks", {}).items():
        spec = record.get("spec", {})
        override = spec.get("config_overrides", {}).get("experiment", {})
        if (spec.get("experiment") != "E4" or override.get("scale_task") != "restore_footprint"
                or record.get("status") != "COMPUTE_DONE"
                or record.get("sync_status") != "VERIFIED"
                or record.get("handle_alive") is not False):
            continue
        run_value = record.get("run_dir")
        if not run_value:
            continue
        summary_path = Path(run_value) / "summary.json"
        if not summary_path.exists():
            continue
        summary = read_json(summary_path)
        if (summary.get("scale_variant") == SCALE_VARIANT
                and summary.get("common_scale_manifest_hash") == context["scale_manifest"]["manifest_hash"]
                and summary.get("profile_hash") == context["profile_hash"]
                and summary.get("correctness_gate") == "PASS"):
            matches.append((identifier, record))
    if len(matches) != 1:
        raise ValueError("E5_PARENT_REQUIRED: verified v3 E4 restore tail is required")
    return matches[0]


def _query_context(cfg, root, context, timing):
    roles = read_json(context["orcas"] / "splits" / "query_roles.json")["roles"]
    # E4's old probe used a diagnostic schedule purpose.  E5 must use the
    # exact group IDs frozen in the common manifest, in its stored order; a
    # second stable sample, even at the same cap, is a protocol violation.
    schedule = list(context["scale_manifest"]["orcas_group_ids"])
    expected_groups = set(schedule)
    wanted = expected_groups | set(roles.get("cal_fit", [])) | set(roles.get("cal_check", []))
    wanted |= set(roles.get("tune", []))
    records = {}
    parquet = pq.ParquetFile(context["orcas"] / "queries.parquet")
    for batch in parquet.iter_batches(columns=["group_id", "text"], batch_size=100_000):
        columns = batch.to_pydict()
        for group_id, text in zip(columns["group_id"], columns["text"]):
            if group_id in wanted:
                records[group_id] = text
        if len(records) == len(wanted):
            break
    if expected_groups - set(records):
        raise ValueError("E5_INPUT_GATE_FAILED: frozen schedule query is missing")
    specs = {}
    from .encoders import model_specs, resolve_model
    for role, spec in model_specs("arctic", root).items():
        specs[role] = resolve_model(spec, cfg["paths"], root)
    query_cfg = deepcopy(cfg)
    query_cfg["models"]["batch_size"] = int(
        context["profile"]["selections"]["runtime"]["batches"]["new"])
    queries = _encode_queries(records, roles, specs["new"], query_cfg, root, timing)
    if any(group not in queries for group in schedule):
        raise ValueError("E5_INPUT_GATE_FAILED: frozen schedule query is missing")
    proxies, join = _traffic_proxies(context["orcas"], schedule,
                                     context["scale_manifest"]["document_rows_array"])
    traffic = SchedulingTraffic(tuple(schedule),
                                np.stack([queries[group] for group in schedule]), proxies)
    calibration_queries = {
        role: {group: queries[group] for group in roles.get(role, []) if group in queries}
        for role in ("cal_fit", "cal_check")}
    return traffic, calibration_queries, join, specs


def _common_calibration(cfg, context, old, new, doc_ids, pools):
    """Freeze calibration document pairs once for the complete E5 matrix."""
    cache = Path(cfg["paths"]["cache"]) / "e5" / "common"
    key = digest({"manifest": context["scale_manifest"]["manifest_hash"],
                  "profile": context["profile_hash"], "pipeline": _scale_pipeline_hash(cfg, context),
                  "cal_cap": pools["cal_cap"]})
    path = cache / f"calibration-{key}.json"
    if path.exists():
        pools_record = read_json(path)
        pools_record.pop("cache_key", None)
        validate_calibration_pools(pools_record, context["calibration_queries"],
                                   set(map(int, pools["train"])) | set(map(int, pools["validation"])),
                                   {role: pools["cal_cap"] for role in ("cal_fit", "cal_check")},
                                   cfg["calibration"], len(doc_ids))
        return pools_record, key
    train = np.asarray(pools["train"], dtype=np.int64)
    proposal = fit_op(old[train], new.get_rows(train))
    reserved = set(map(int, train)) | set(map(int, pools["validation"]))
    caps = {role: pools["cal_cap"] for role in ("cal_fit", "cal_check")}
    result = make_calibration_proposal(
        proposal, context["calibration_queries"], old, doc_ids, caps, reserved,
        cfg["calibration"], cfg["splits"]["master_seed"])
    validate_calibration_pools(result, context["calibration_queries"], reserved,
                               caps, cfg["calibration"], len(doc_ids))
    cache.mkdir(parents=True, exist_ok=True)
    write_json(cache / f"calibration-{key}.part.json", {**result, "cache_key": key})
    (cache / f"calibration-{key}.part.json").replace(path)
    return result, key


def _reference_rows(cfg, context, new, doc_ids, traffic):
    cache = Path(cfg["paths"]["cache"]) / "e5" / "references"
    vector_key = new.base.manifest["cache_key"] if hasattr(new, "base") else new.manifest["cache_key"]
    key = digest({"manifest": context["scale_manifest"]["manifest_hash"],
                  "vectors": vector_key, "traffic": traffic.fingerprint})
    path = cache / f"reference-{key}.npz"
    marker = cache / f"reference-{key}.json"
    if path.exists() and marker.exists():
        meta = read_json(marker)
        rows = np.load(path, allow_pickle=False)["rows"]
        if meta.get("key") == key and tuple(rows.shape) == (len(traffic.query_ids), 11):
            return rows, {"cache_key": key, "cache_hit": True, "rows": len(rows)}
    target = new.get_rows(np.arange(len(doc_ids), dtype=np.int64))
    exact = ExactIndex(target, doc_ids, np.ones(len(doc_ids), dtype=bool), chunk_rows=cfg["search"]["chunk_rows"])
    result = exact.search(traffic.vectors)
    rows = np.asarray(result.rows, dtype=np.int64)
    if rows.shape != (len(traffic.query_ids), 11):
        raise ValueError("E5_REFERENCE_FAILED: full-new exact reference shape differs")
    cache.mkdir(parents=True, exist_ok=True)
    part = path.with_suffix(".part.npz")
    np.savez(part, rows=rows)
    part.replace(path)
    write_json(marker, {"key": key, "rows": len(rows), "query_fingerprint": traffic.fingerprint})
    return rows, {"cache_key": key, "cache_hit": False, "rows": len(rows)}


def _arr_at_10(rows, reference):
    values = [len(set(map(int, left[:10])) & set(map(int, right[:10]))) / 10.0
              for left, right in zip(rows, reference)]
    return float(np.mean(values)) if values else None


def _write_events(path, events):
    atomic_bytes(path, "".join(json.dumps(event, sort_keys=True) + "\n"
                                for event in events).encode())


def _run_dir(cfg, scheduler, map_seed, traffic_seed, locked):
    return Path(cfg["paths"]["runs"]) / (
        f"E5-scale-{scheduler}-m{map_seed}-t{traffic_seed}-{digest(locked)[:12]}")


def run_e5_cell(cfg, root):
    root = Path(root)
    if cfg["execution"]["phase"] != "official" or cfg["execution"]["mode"] != "cached_access":
        raise ValueError("E5 cells require official/cached_access")
    require_target_hardware(cfg, probe_hardware())
    _hint_id, _hint_record, _hint_summary, _hint_dir, attestation = \
        _find_parent_release_attestation(cfg, root)
    context = _profile_context(
        cfg, root, ann_parent_verified=True,
        validated_releases={"documents": attestation["documents"],
                            "orcas": attestation["orcas"]})
    parent = _find_verified_e4_parent(cfg, root, context)
    pipeline_hash = _scale_pipeline_hash(cfg, context)
    scheduler = cfg["scheduler"]["kind"]
    map_seed = int(cfg["experiment"]["map_seed"])
    traffic_seed = int(cfg["experiment"]["traffic_seed"])
    if scheduler not in E5_SCHEDULERS or map_seed not in E5_MAP_SEEDS or traffic_seed != E5_TRAFFIC_SEED:
        raise ValueError("E5_CELL_INVALID: scheduler/seed is outside the compact primary matrix")
    locked = {
        "config": redacted_config(cfg), "source_hash": source_hash(root),
        "run_budget_policy": RUN_BUDGET_POLICY, "scale_variant": SCALE_VARIANT,
        "common_scale_manifest_hash": context["scale_manifest"]["manifest_hash"],
        "profile_hash": context["profile_hash"], "pipeline_hash": pipeline_hash,
        "parent_e4_artifact_id": parent["artifact_id"],
        "parent_e4_artifact_hash": parent["artifact_hash"],
        "official_doc_pool": DOCUMENT_CAP, "orcas_group_cap": ORCAS_GROUP_CAP,
        "claim_scope": "reduced_scale_pilot", "cell_role": "required",
        "scheduler": scheduler, "map_seed": map_seed, "traffic_seed": traffic_seed,
    }
    run_dir = _run_dir(cfg, scheduler, map_seed, traffic_seed, locked)
    if (run_dir / "summary.json").exists():
        summary = read_json(run_dir / "summary.json")
        if summary.get("compute_status") == "COMPUTE_DONE":
            return finalize_run(run_dir, summary, cfg, root)
        raise ValueError("Failed E5 cell is preserved; enqueue a new immutable source revision")
    run_dir.mkdir(parents=True, exist_ok=True)
    write_json(run_dir / "config.lock.json", locked)
    write_json(run_dir / "environment.json", probe_hardware())
    write_json(run_dir / "dataset_manifest.json", {
        "documents": context["docs_manifest"], "orcas": context["orcas_manifest"],
        "common_scale": {key: value for key, value in context["scale_manifest"].items()
                          if key not in {"document_rows_array", "path"}},
        "parent_e4": {"artifact_id": parent["artifact_id"], "artifact_hash": parent["artifact_hash"]},
    })
    write_json(run_dir / "reference_inputs.json", {
        "parent_e4_artifact_id": parent["artifact_id"],
        "parent_e4_artifact_hash": parent["artifact_hash"],
        "common_scale_manifest_hash": context["scale_manifest"]["manifest_hash"],
        "pipeline_hash": pipeline_hash, "quality_labels_opened": False,
        "judged_metrics": "N/A_REDUCED_COVERAGE",
        "claim_scope": "reduced_scale_pilot",
    })
    write_json(run_dir / "tuning_profile.json", {
        "profile_hash": context["profile_hash"], **context["profile"]})
    snapshot_source(root, run_dir)
    run_id = run_dir.name
    update_checklist(root, run_id, {"compute_status": "RUNNING", "sync_status": "PENDING",
                                    "outcome": "inconclusive", "expect_classification": "KHỚP"})
    timing, events, checkpoint_metrics = [], [], []
    summary = {
        "compute_status": "FAILED", "phase": "official", "outcome": "inconclusive",
        "expect_classification": "KHỚP", "performance_claim": False,
        "run_budget_policy": RUN_BUDGET_POLICY, "scale_variant": SCALE_VARIANT,
        "official_doc_pool": DOCUMENT_CAP, "orcas_group_cap": ORCAS_GROUP_CAP,
        "claim_scope": "reduced_scale_pilot", "cell_role": "required",
        "scheduler": scheduler, "map_seed": map_seed, "traffic_seed": traffic_seed,
        "profile_hash": context["profile_hash"], "pipeline_hash": pipeline_hash,
        "common_scale_manifest_hash": context["scale_manifest"]["manifest_hash"],
        "parent_e4_artifact_id": parent["artifact_id"],
        "parent_e4_artifact_hash": parent["artifact_hash"],
    }
    try:
        _store, old, new, specs = _encode_full_vectors(cfg, context, root, timing)
        full_doc_ids = (context["docs"] / "doc_ids.txt").read_text().splitlines()
        doc_ids = [full_doc_ids[int(row)]
                   for row in context["scale_manifest"]["document_rows_array"]]
        if len(old) != DOCUMENT_CAP or len(new) != DOCUMENT_CAP:
            raise ValueError("E5_INPUT_GATE_FAILED: vector cache rows differ from 50k manifest")
        pools = sample_document_pools(doc_ids, cfg)
        traffic, calibration_queries, join, query_specs = _query_context(cfg, root, context, timing)
        context["calibration_queries"] = calibration_queries
        fixed_calibration, calibration_key = _common_calibration(
            cfg, context, old, new, doc_ids, pools)
        reference, reference_meta = _reference_rows(cfg, context, new, doc_ids, traffic)
        write_json(run_dir / "common_calibration.json", {
            "cache_key": calibration_key, **fixed_calibration,
            "query_roles": {role: sorted(values) for role, values in calibration_queries.items()},
        })
        write_json(run_dir / "reference_inputs.json", {
            **read_json(run_dir / "reference_inputs.json"),
            "traffic_fingerprint": traffic.fingerprint, "query_groups": len(traffic.query_ids),
            "orcas_join": join, "reference": reference_meta,
            "models": {role: {key: value for key, value in spec.items() if key != "snapshot"}
                       for role, spec in query_specs.items()},
        })
        candidate = deepcopy(cfg)
        candidate["mapping"]["kind"] = "residual_mlp"
        selected_map = context["profile"]["selections"]["map"]["residual_mlp"]
        if selected_map.get("lr") is not None:
            candidate["mapping"]["lr"] = selected_map["lr"]
        selected_search = context["profile"]["selections"]["search"]
        candidate["search"].update(backend="hnsw", candidates=int(selected_search["candidates"]),
                                    ef_search=int(selected_search["ef_search"]),
                                    # T0.scale freezes encoder batches and
                                    # HNSW L/ef; its runtime selection predates
                                    # the core thread probe and has no
                                    # ``runtime.threads`` entry.  E4 used the
                                    # explicit scale config value, so reuse it
                                    # for every E5 cell.
                                    threads=int(cfg["search"]["threads"]))
        accessor = PaidEmbeddingAccessor(
            lambda rows: new.get_rows(rows),
            {"train": pools["train"], "validation": pools["validation"],
             "backfill": set(range(DOCUMENT_CAP)) - set(map(int, pools["train"]))
                         - set(map(int, pools["validation"]))},
            DOCUMENT_CAP, mode="cached_access", journal=run_dir / "access-journal.json")
        if accessor.paid:
            raise ValueError("E5_ACCESS_GATE_FAILED: fresh cell has a nonempty access journal")
        with _cost(timing, "migration_bootstrap"):
            state = bootstrap_migration(
                doc_ids, pools, old, accessor, candidate, map_seed=map_seed,
                traffic_seed=traffic_seed, calibration_queries=calibration_queries,
                fixed_calibration_pools=fixed_calibration)
        initial_paid = len(accessor.paid)
        checkpoint_metrics.append({"checkpoint": "bootstrap", "accessed": initial_paid,
                                   "f_accessed": initial_paid / DOCUMENT_CAP,
                                   "arr_at_10": _arr_at_10(
                                       state.index.search(traffic.vectors).rows, reference)})
        emit_checkpoint(state, run_dir / "checkpoints", f"bootstrap-{initial_paid:09d}",
                        digest(locked))
        for fraction in (0.05, 0.10, 0.25, 0.50, 1.0):
            target = int(np.floor(fraction * DOCUMENT_CAP))
            if target <= len(accessor.paid):
                checkpoint_metrics.append({"checkpoint": fraction, "accessed": len(accessor.paid),
                                           "f_accessed": len(accessor.paid) / DOCUMENT_CAP,
                                           "status": "covered_by_previous_checkpoint"})
                continue
            with _cost(timing, f"migration_to_{int(fraction * 100)}pct"):
                result = run_migration(state, [target], traffic=traffic)
            events.extend(result["events"])
            arr = _arr_at_10(state.index.search(traffic.vectors).rows, reference)
            row = {"checkpoint": fraction, "accessed": len(accessor.paid),
                   "f_accessed": len(accessor.paid) / DOCUMENT_CAP, "arr_at_10": arr,
                   "events": len(result["events"]),
                   "greedy_count": sum(event.get("greedy_count", 0) for event in result["events"]),
                   "fallback_count": sum(event.get("fallback_count", 0) for event in result["events"])}
            checkpoint_metrics.append(row)
            emit_checkpoint(state, run_dir / "checkpoints", f"accessed-{len(accessor.paid):09d}",
                            digest(locked))
            print(f"{run_id}: {len(accessor.paid)}/{DOCUMENT_CAP} accessed; checkpoint saved",
                  flush=True)
        if len(accessor.paid) != DOCUMENT_CAP or len(set(accessor.order)) != DOCUMENT_CAP:
            raise ValueError("E5_COMPLETION_FAILED: 100% true paid budget is not unique")
        final_checkpoint = max((path for path in (run_dir / "checkpoints").glob("*")
                                if (path / "checkpoint.json").exists()),
                               key=lambda path: read_json(path / "checkpoint.json")["paid"])
        restored_accessor = PaidEmbeddingAccessor(
            lambda rows: new.get_rows(rows), accessor.roles, DOCUMENT_CAP, mode="cached_access")
        restored = restore_migration(final_checkpoint, old, restored_accessor, candidate, digest(locked))
        if not np.array_equal(restored.index.vectors, state.index.vectors):
            raise ValueError("E5_RESTORE_FAILED: final checkpoint vectors differ")
        final_exact = ExactIndex(new.get_rows(np.arange(DOCUMENT_CAP, dtype=np.int64)), doc_ids,
                                 np.ones(DOCUMENT_CAP, dtype=bool), chunk_rows=cfg["search"]["chunk_rows"])
        completion = _arr_at_10(final_exact.search(traffic.vectors).rows, reference)
        np.savez(run_dir / "accessed_ids.npz", paid=np.asarray(accessor.order, dtype=np.int64),
                 backfilled=np.asarray(state.backfilled, dtype=np.int64), train=pools["train"],
                 validation=pools["validation"], cal_fit=fixed_calibration["cal_fit"]["rows"],
                 cal_check=fixed_calibration["cal_check"]["rows"])
        _write_events(run_dir / "events.jsonl", events)
        write_json(run_dir / "e5_metrics.json", {
            "scheduler": scheduler, "map_seed": map_seed, "traffic_seed": traffic_seed,
            "arr_at_10": next((row["arr_at_10"] for row in checkpoint_metrics
                                if row.get("checkpoint") == 0.10), None),
            "checkpoint_metrics": checkpoint_metrics, "completion_full_new_arr": completion,
            "judged_metrics": "N/A_REDUCED_COVERAGE", "orcas_join": join,
            "quality_labels_opened": False,
        })
        write_json(run_dir / "timing.json", {"records": timing,
                                              "migration": state.cost_records,
                                              "accessor": accessor.cost,
                                              "peak_rss_bytes": _peak_rss_bytes(),
                                              "performance_claim": False,
                                              "exclusive": "unverified"})
        if source_hash(root) != locked["source_hash"]:
            raise ValueError("SOURCE_CHANGED_DURING_RUN")
        summary.update({"compute_status": "COMPUTE_DONE", "correctness_gate": "PASS",
                        "quality_gate": "MEASURED", "documents": DOCUMENT_CAP,
                        "orcas_schedule_groups": len(traffic.query_ids),
                        "orcas_join": join, "unique_paid_documents": DOCUMENT_CAP,
                        "bootstrap_paid": initial_paid,
                        "primary_arr_at_10": next((row["arr_at_10"] for row in checkpoint_metrics
                                                   if row.get("checkpoint") == 0.10), None),
                        "completion_full_new_arr": completion,
                        "checkpoints": checkpoint_metrics,
                        "calibration_pool_key": calibration_key,
                        "search": {"candidates": candidate["search"]["candidates"],
                                   "ef_search": candidate["search"]["ef_search"]},
                        "target_hardware_pass": True})
    except Exception as exc:
        summary.update(error_type=type(exc).__name__, reason=str(exc))
        write_json(run_dir / "e5_metrics.json", {"status": "FAILED", "reason": summary["reason"]})
        write_json(run_dir / "timing.json", {"records": timing, "performance_claim": False})
    return finalize_run(run_dir, summary, cfg, root)


class _cost:
    """Small local timing context to keep E5 records uniform with other runners."""
    def __init__(self, records, component):
        self.records, self.component = records, component

    def __enter__(self):
        self.started = time.monotonic()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.records.append({"component": self.component,
                             "wall_seconds": time.monotonic() - self.started,
                             "source": "measured"})
        return False


def build_e5_tasks(cfg, root):
    """Build the serial 12-cell E5 primary matrix behind verified E4."""
    root = Path(root)
    if cfg.get("experiment", {}).get("run_budget_policy") != RUN_BUDGET_POLICY:
        raise ValueError(f"E5 runner requires run_budget_policy={RUN_BUDGET_POLICY}")
    profiles = load_tuning_profiles(root / cfg["tuning"]["lock_path"])
    scale_profiles = [(key, value) for key, value in profiles["profiles"].items()
                      if value.get("scope") == "scale"]
    if len(scale_profiles) != 1:
        raise ValueError("E5_PROFILE_REQUIRED: exactly one frozen T0.scale profile is required")
    profile_hash, profile = scale_profiles[0]
    # The e5 config intentionally leaves parent-specific values null.  Resolve
    # the immutable manifest/profile context only while building the job graph.
    resolved = deepcopy(cfg)
    resolved["experiment"].update(
        profile_hash=profile_hash, tuning_scope="scale", scale_variant=SCALE_VARIANT)
    from .scale_manifest import load_common_manifest, manifest_path
    manifest = load_common_manifest(resolved, root, profile["selections"]["source_run"])
    resolved["experiment"]["scale_manifest_hash"] = manifest["manifest_hash"]
    resolved["experiment"]["scale_manifest_path"] = manifest_path(resolved, root).relative_to(root).as_posix()
    release_attestation = {
        "documents": read_json(root / "data/processed/msmarco-docs-v1/manifest.json"),
        "orcas": read_json(root / "data/processed/orcas/manifest.json"),
    }
    context = _profile_context(resolved, root, ann_parent_verified=True,
                               validated_releases=release_attestation)
    parent = _find_verified_e4_parent(resolved, root, context)
    tail_id, _tail = _find_verified_e4_tail(resolved, root, context)
    pipeline_hash = _scale_pipeline_hash(resolved, context)
    revision = digest({"source": source_hash(root), "profile": profile_hash,
                       "manifest": manifest["manifest_hash"], "parent": parent["artifact_hash"],
                       "pipeline": pipeline_hash, "matrix": {
                           "schedulers": E5_SCHEDULERS, "map_seeds": E5_MAP_SEEDS,
                           "traffic_seed": E5_TRAFFIC_SEED}})[:12]
    common = {
        "config": "configs/experiments/e5.yaml", "phase": "official",
        "measurement_mode": "exclusive", "development_hardware": False,
        "tuning_scope": "scale", "input_refs": profile["inputs"],
        "profile_hash": profile_hash, "variant_id": "primary", "overrides": {},
        "allow_ann_from_verified_parent": True,
        "run_budget_policy": RUN_BUDGET_POLICY,
        "resources": {"gpu_device": 0, "gpu_memory_gib": 16, "host_ram_gib": 64,
                       "cpu_cores": 8, "disk_scratch_gib": 96, "io_heavy": True},
    }
    tasks, previous = [], tail_id
    for scheduler in E5_SCHEDULERS:
        for map_seed in E5_MAP_SEEDS:
            task_id = f"E5.primary.{scheduler}.m{map_seed}.t{E5_TRAFFIC_SEED}.{revision}"
            overrides = {"experiment": {
                "profile_hash": profile_hash, "tuning_scope": "scale",
                "run_budget_policy": RUN_BUDGET_POLICY, "cell_role": "required",
                "map_seed": map_seed, "traffic_seed": E5_TRAFFIC_SEED,
                "scale_variant": SCALE_VARIANT,
                "scale_manifest_hash": manifest["manifest_hash"],
                "scale_manifest_path": resolved["experiment"]["scale_manifest_path"],
                "source_run": context["source_run"]},
                "scheduler": {"kind": scheduler},
                "mapping": {"kind": "residual_mlp"}}
            tasks.append({**common, "task_id": task_id, "experiment": "E5",
                          "config_overrides": overrides, "depends_on": [previous],
                          "priority": 60, "cell_role": "required",
                          "scale_variant": SCALE_VARIANT,
                          "common_scale_manifest_hash": manifest["manifest_hash"],
                          "parent_e4_artifact_id": parent["artifact_id"],
                          "parent_e4_artifact_hash": parent["artifact_hash"],
                          "pipeline_hash": pipeline_hash})
            previous = task_id
    from .queue import validate_jobs
    return validate_jobs(tasks)
