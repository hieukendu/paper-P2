"""Scale-scope preparation and readiness probes.

The scale preparation is deliberately separate from the E2 quality runner.  It
uses the validated MS MARCO/ORCAS inputs, a fixed uniform subset, and the
same migration primitives as the official cells.  No judged-dev result is
read while selecting map/runtime settings.
"""

from copy import deepcopy
from pathlib import Path
import time

import numpy as np
import pyarrow.parquet as pq

from .config import freeze_tuning_profile, redacted_config
from .data.prepare import validate_prepared
from .data.splits import sample_document_pools, stable_key
from .data.store import DocumentStore
from .encoders import build_encoder, model_specs, resolve_model
from .experiments import (_completed_prerequisite, finalize_run, hardware_identity,
                          select_map_hyperparameters, source_hash)
from .hf_sync import snapshot_source
from .io import digest, file_digest, read_json, write_json
from .maps import save_map_state
from .migration import (bootstrap_migration, emit_checkpoint, restore_migration,
                        run_migration)
from .runtime import probe_hardware, probe_storage, require_target_hardware
from .scheduling import SchedulingTraffic
from .vectors import PaidEmbeddingAccessor


SCALE_SUBSET_SIZE = 100_000
SCALE_SEED = 20261020
SCALE_GROUP_CAP = 10_000
SCALE_TASKS = ("subset_probe", "full_bootstrap", "restore_footprint")


def _scale_paths(cfg):
    data = Path(cfg["paths"]["data"]) / "processed"
    return data / "msmarco-docs-v1", data / "orcas"


def _scale_inputs(cfg, root):
    docs, orcas = _scale_paths(cfg)
    docs_manifest = validate_prepared(docs)
    orcas_manifest = validate_prepared(orcas)
    if orcas_manifest.get("documents_release_hash") != docs_manifest["release_hash"]:
        raise ValueError("ORCAS document release differs from MS MARCO release")
    specs = {role: resolve_model(spec, cfg["paths"], root)
             for role, spec in model_specs("arctic", root).items()}
    environment = probe_hardware()
    require_target_hardware(cfg, environment)
    refs = {"dataset": "msmarco-docs-v1", "release": docs_manifest["release_hash"],
            "orcas_release": orcas_manifest["release_hash"],
            "orcas_split_hash": orcas_manifest["split_hash"], "pair": "arctic",
            "subset_size": SCALE_SUBSET_SIZE, "subset_seed": SCALE_SEED,
            "models": {role: {k: v for k, v in spec.items() if k != "snapshot"}
                       for role, spec in specs.items()}, "hardware": hardware_identity(environment)}
    return docs, orcas, docs_manifest, orcas_manifest, specs, environment, refs


def _uniform_subset(doc_ids):
    if len(doc_ids) < SCALE_SUBSET_SIZE:
        raise ValueError("MS MARCO corpus is smaller than the required 100k subset")
    rows = sorted(range(len(doc_ids)), key=lambda row: stable_key(SCALE_SEED, "scale-subset", doc_ids[row]))
    return np.asarray(rows[:SCALE_SUBSET_SIZE], dtype=np.int64)


def _encode_rows(store, rows, spec, cfg, output, key, timing, role, batch_size=None):
    """Encode fixed rows into a checksummed local cache without loading text all at once."""
    output = Path(output)
    marker = output / "manifest.json"
    if marker.exists():
        meta = read_json(marker)
        if meta.get("cache_key") != key:
            raise ValueError(f"{role} vector cache key mismatch")
        array = np.load(output / "vectors.npy", mmap_mode="r", allow_pickle=False)
        if tuple(array.shape) != (len(rows), spec["dim"]):
            raise ValueError(f"{role} vector cache shape mismatch")
        if file_digest(output / "vectors.npy") != meta["sha256"]:
            raise ValueError(f"{role} vector cache checksum mismatch")
        return array, {**meta, "cache_hit": True}
    output.mkdir(parents=True, exist_ok=True)
    encoder = build_encoder(spec, cfg["execution"]["device"],
                            int(batch_size or cfg["models"]["batch_size"]))
    try:
        values = np.lib.format.open_memmap(output / "vectors.part.npy", mode="w+",
                                           dtype=np.float32, shape=(len(rows), spec["dim"]))
        for start in range(0, len(rows), encoder.batch_size):
            selected = rows[start:start + encoder.batch_size]
            documents = store.get_documents(selected.tolist())
            values[start:start + len(selected)] = encoder.encode_documents([d.text for d in documents])
            if start and start % (encoder.batch_size * 128) == 0:
                print(f"scale {role}: {start}/{len(rows)}", flush=True)
        values.flush()
        del values
        (output / "vectors.part.npy").replace(output / "vectors.npy")
        meta = {"cache_key": key, "rows": len(rows), "dim": spec["dim"],
                "sha256": file_digest(output / "vectors.npy"),
                "encoder_cost": dict(encoder.cost), "role": role}
        write_json(marker, meta)
        timing.append({"component": f"encode_{role}", "wall_seconds": encoder.cost["wall_seconds"],
                       "documents": len(rows), "cache_hit": False, "source": "measured"})
        return np.load(output / "vectors.npy", mmap_mode="r", allow_pickle=False), meta
    finally:
        encoder.close()


def _query_records(orcas_path, roles):
    wanted = set().union(*(set(roles.get(role, [])) for role in ("cal_fit", "cal_check", "tune")))
    schedule = sorted(roles.get("schedule", []),
                      key=lambda value: stable_key(SCALE_SEED, "scale-schedule-sample", value))[:SCALE_GROUP_CAP]
    wanted.update(schedule)
    records = {}
    parquet = pq.ParquetFile(orcas_path / "queries.parquet")
    for batch in parquet.iter_batches(columns=["group_id", "text"], batch_size=100_000):
        columns = batch.to_pydict()
        for group_id, text in zip(columns["group_id"], columns["text"]):
            if group_id in wanted:
                records[group_id] = text
        if len(records) == len(wanted):
            break
    missing = wanted - set(records)
    if missing:
        raise ValueError(f"ORCAS query groups missing from validated parquet: {len(missing)}")
    return records, schedule


def _traffic_proxies(orcas_path, schedule, subset_rows):
    local = {int(row): i for i, row in enumerate(map(int, subset_rows))}
    wanted = set(schedule)
    proxies = {group: set() for group in schedule}
    parquet = pq.ParquetFile(orcas_path / "traffic.parquet")
    for batch in parquet.iter_batches(columns=["group_id", "doc_row"], batch_size=1_000_000):
        columns = batch.to_pydict()
        for group_id, row in zip(columns["group_id"], columns["doc_row"]):
            if group_id in wanted and int(row) in local:
                proxies[group_id].add(local[int(row)])
    return [proxies[group] for group in schedule], {
        "groups": len(schedule), "groups_with_joined_edges": sum(bool(v) for v in proxies.values()),
        "candidate_empty_groups": sum(not v for v in proxies.values()),
    }


def _encode_queries(records, roles, spec, cfg, root, timing):
    order = []
    for role in ("cal_fit", "cal_check", "tune", "schedule"):
        for group in roles.get(role, []):
            if group not in order and group in records:
                order.append(group)
    encoder = build_encoder(spec, cfg["execution"]["device"], cfg["models"]["batch_size"])
    try:
        values = np.empty((len(order), spec["dim"]), dtype=np.float32)
        started = time.monotonic()
        for start in range(0, len(order), 128):
            values[start:start + 128] = encoder.encode_queries(
                [records[group] for group in order[start:start + 128]])
        timing.append({"component": "encode_scale_queries", "wall_seconds": time.monotonic() - started,
                       "queries": len(order), "source": "measured"})
    finally:
        encoder.close()
    return {group: values[i] for i, group in enumerate(order)}


def _run_scale_scheduler_probe(doc_ids, old, new, pools, cfg, queries, roles, schedule,
                               proxies, run_dir, timing):
    probe_cfg = deepcopy(cfg)
    probe_cfg["mapping"]["kind"] = "residual_mlp"
    probe_cfg["search"].update(backend="hnsw", candidates=50, ef_search=200, threads=8)
    traffic = SchedulingTraffic(tuple(schedule), np.stack([queries[group] for group in schedule]), proxies)
    cal = {role: {group: queries[group] for group in roles.get(role, []) if group in queries}
           for role in ("cal_fit", "cal_check")}
    results = []
    for scheduler in ("random", "degree", "read", "greedy"):
        candidate = deepcopy(probe_cfg)
        candidate["scheduler"]["kind"] = scheduler
        def source(rows):
            return new[np.asarray(rows, dtype=np.int64)]
        accessor = PaidEmbeddingAccessor(source, {"train": pools["train"],
                    "validation": pools["validation"], "backfill": set(range(len(doc_ids))) -
                    set(pools["train"]) - set(pools["validation"])}, len(doc_ids), "cached_access")
        started = time.monotonic()
        state = bootstrap_migration(doc_ids, pools, old, accessor, candidate,
                                    map_seed=17, traffic_seed=101, calibration_queries=cal)
        initial = len(accessor.paid)
        first = run_migration(state, [max(initial, int(.10 * len(doc_ids)))], traffic=traffic)
        paid_at_10pct = len(accessor.paid)
        events_10pct = len(first["events"])
        second = run_migration(state, [max(len(accessor.paid), int(.25 * len(doc_ids)))], traffic=traffic)
        checkpoint = emit_checkpoint(state, run_dir / "checkpoints", f"{scheduler}-25pct",
                                     digest({"scheduler": scheduler, "n": len(doc_ids)}))
        restored_accessor = PaidEmbeddingAccessor(source, accessor.roles, len(doc_ids), "cached_access")
        restored = restore_migration(checkpoint, old, restored_accessor, candidate,
                                     digest({"scheduler": scheduler, "n": len(doc_ids)}))
        if not np.array_equal(restored.index.vectors, state.index.vectors):
            raise ValueError(f"Scale scheduler restore differs for {scheduler}")
        row = {"scheduler": scheduler, "initial_paid": initial,
               "paid_at_10pct": paid_at_10pct, "events_10pct": events_10pct,
               "events_to_25pct": len(second["events"]),
               "greedy_count": sum(e.get("greedy_count", 0) for e in first["events"] + second["events"]),
               "fallback_count": sum(e.get("fallback_count", 0) for e in first["events"] + second["events"]),
               "elapsed_seconds": time.monotonic() - started, "restore": "PASS"}
        results.append(row)
        timing.append({"component": f"scheduler_{scheduler}_10_to_25pct",
                       "wall_seconds": row["elapsed_seconds"], "source": "measured"})
    return results


def run_scale_presetup(task, cfg):
    root = Path(task["root"])
    cfg = deepcopy(cfg)
    cfg["dataset"]["name"] = "msmarco-docs-v1"
    cfg["models"]["pair"] = "arctic"
    cfg["tuning"]["scope"] = "scale"
    cfg["execution"]["mode"] = "cached_access"
    cfg["execution"]["phase"] = "development"
    docs, orcas, docs_manifest, orcas_manifest, specs, environment, refs = _scale_inputs(cfg, root)
    runtime_dir = _completed_prerequisite(cfg, root, "RUNTIME_PROBE",
                                          docs_manifest["release_hash"], "arctic")
    runtime_path = runtime_dir / "throughput_probe.json"
    runtime = read_json(runtime_path)
    if hardware_identity(runtime["environment"]) != hardware_identity(environment):
        raise ValueError("RUNTIME_PROBE_REQUIRED: runtime hardware or dependencies changed")
    batches = {role: int(runtime["results"][role]["selected_batch_size"])
               for role in ("old", "new")}
    if any(value < 1 for value in batches.values()):
        raise ValueError("RUNTIME_PROBE_REQUIRED: invalid selected batch size")
    refs["runtime_probe_run"] = runtime_dir.name
    refs["runtime_probe_hash"] = file_digest(runtime_path)
    refs["runtime_batches"] = batches
    doc_ids = (docs / "doc_ids.txt").read_text().splitlines()
    subset_rows = _uniform_subset(doc_ids)
    refs["subset_hash"] = digest([doc_ids[int(row)] for row in subset_rows])
    locked = {"source_hash": source_hash(root), "config": redacted_config(cfg),
              "input_refs": refs, "data_release": docs_manifest["release_hash"],
              "orcas_release": orcas_manifest["release_hash"]}
    run_dir = Path(cfg["paths"]["runs"]) / f"T0-scale-msmarco-arctic-{digest(locked)[:12]}"
    run_dir.mkdir(parents=True, exist_ok=True)
    if (run_dir / "summary.json").exists():
        return finalize_run(run_dir, read_json(run_dir / "summary.json"), cfg, root)
    write_json(run_dir / "config.lock.json", locked)
    write_json(run_dir / "dataset_manifest.json", {"documents": docs_manifest, "orcas": orcas_manifest})
    write_json(run_dir / "environment.json", environment)
    write_json(run_dir / "models.lock.json", {r: {k: v for k, v in s.items() if k != "snapshot"}
                                                for r, s in specs.items()})
    write_json(run_dir / "subset_manifest.json", {"seed": SCALE_SEED, "rows": len(subset_rows),
               "ids_sha256": digest([doc_ids[int(row)] for row in subset_rows]),
               "rows_path": "subset_rows.npy"})
    np.save(run_dir / "subset_rows.npy", subset_rows)
    snapshot_source(root, run_dir)
    write_json(run_dir / "throughput_probe.json", runtime)
    timing, summary = [], {"compute_status": "FAILED", "phase": "development",
                           "outcome": "diagnostic", "performance_claim": False,
                           "run_budget_policy": "compact_v1", "scope": "T0.scale",
                           "expect_classification": "KHỚP"}
    try:
        store = DocumentStore(docs)
        subset_ids = [doc_ids[int(row)] for row in subset_rows]
        pools = sample_document_pools(subset_ids, cfg)
        cfg["experiment"]["scale_release"] = docs_manifest["release_hash"]
        old_key = digest({"release": docs_manifest["release_hash"], "model": specs["old"],
                          "rows": subset_rows.tolist(), "role": "scale_old_subset"})
        new_key = digest({"release": docs_manifest["release_hash"], "model": specs["new"],
                          "rows": subset_rows.tolist(), "role": "scale_new_subset"})
        old, old_meta = _encode_rows(store, subset_rows, specs["old"], cfg,
                                     Path(cfg["paths"]["cache"]) / "vectors/scale-old" / old_key,
                                     old_key, timing, "scale_old_subset", batches["old"])
        new, new_meta = _encode_rows(store, subset_rows, specs["new"], cfg,
                                     Path(cfg["paths"]["cache"]) / "vectors/scale-new" / new_key,
                                     new_key, timing, "scale_new_subset", batches["new"])
        selected, table = select_map_hyperparameters(
            (old[pools["train"]], new[pools["train"]]),
            (old[pools["validation"]], new[pools["validation"]]), cfg, seed=17)
        import pyarrow as pa
        pq.write_table(pa.Table.from_pylist(table), run_dir / "selection.parquet")
        roles = read_json(orcas / "splits/query_roles.json")["roles"]
        records, schedule = _query_records(orcas, roles)
        query_cfg = deepcopy(cfg)
        query_cfg["models"]["batch_size"] = batches["new"]
        queries = _encode_queries(records, roles, specs["new"], query_cfg, root, timing)
        proxies, join = _traffic_proxies(orcas, schedule, subset_rows)
        scheduler_rows = _run_scale_scheduler_probe(subset_ids, old, new, pools, cfg,
                                                     queries, roles, schedule, proxies, run_dir, timing)
        map_cfg = deepcopy(cfg)
        map_cfg["mapping"]["kind"] = "residual_mlp"
        map_cfg["search"]["backend"] = "exact"
        if selected["residual_mlp"]["lr"] is not None:
            map_cfg["mapping"]["lr"] = selected["residual_mlp"]["lr"]
        from .maps import fit_global_map
        model, record = fit_global_map("residual_mlp",
                                       (old[pools["train"]], new[pools["train"]]),
                                       (old[pools["validation"]], new[pools["validation"]]),
                                       map_cfg["mapping"], 17)
        save_map_state(model, run_dir / "scale_map.safetensors")
        np.save(run_dir / "q_tune.npy", np.stack([queries[q] for q in roles["tune"] if q in queries]))
        np.save(run_dir / "subset_new.npy", np.asarray(new))
        write_json(run_dir / "scale_metrics.json", {"subset_size": len(subset_rows),
                   "subset_seed": SCALE_SEED, "orcas_join": join,
                   "scheduler_rows": scheduler_rows, "map_selection": selected,
                   "map_fit": record, "old_cache": old_meta, "new_cache": new_meta,
                   "q_tune": len(roles["tune"]), "schedule_groups": len(schedule)})
        write_json(run_dir / "timing.json", {"records": timing, "storage": probe_storage(Path(cfg["paths"]["runs"])),
                   "performance_claim": False, "exclusive": "unverified"})
        estimate = {"scope": "T0.scale", "run_budget_policy": "compact_v1", "concurrency": 1,
                    "measured": {r["component"]: r["wall_seconds"] for r in timing},
                    "full_corpus_encode": "unmeasured_until_E4", "full_graph": "unmeasured_until_E4"}
        write_json(run_dir / "estimate.json", estimate)
        selections = {"map": selected, "search": {"status": "SUBSET_ONLY", "candidates": 50,
                     "ef_search": 200}, "runtime": {"subset_rows": len(subset_rows),
                     "batches": batches, "probe_run": runtime_dir.name,
                     "old": old_meta.get("encoder_cost"), "new": new_meta.get("encoder_cost")},
                     "correctness_pass": True, "local_restore_pass": True,
                     "target_hardware_pass": True, "timing_ref": f"{run_dir.name}/timing.json",
                     "estimate_ref": f"{run_dir.name}/estimate.json", "source_run": run_dir.name,
                     "subset_manifest": f"{run_dir.name}/subset_manifest.json",
                     "q_tune_ref": f"{run_dir.name}/q_tune.npy", "map_ref": f"{run_dir.name}/scale_map.safetensors"}
        profile_hash = freeze_tuning_profile("scale", selections, refs, cfg, root)
        write_json(run_dir / "tuning_profile.json", {"profile_hash": profile_hash,
                   "scope": "scale", "selections": selections, "inputs": refs})
        summary.update(compute_status="COMPUTE_DONE", profile_hash=profile_hash,
                       input_refs=refs, subset_size=len(subset_rows), orcas_join=join,
                       scheduler_rows=scheduler_rows, ann_status="SUBSET_ONLY",
                       local_restore="PASS")
    except Exception as exc:
        summary.update(error_type=type(exc).__name__, reason=str(exc))
        write_json(run_dir / "timing.json", {"records": timing, "performance_claim": False})
    return finalize_run(run_dir, summary, cfg, root)

