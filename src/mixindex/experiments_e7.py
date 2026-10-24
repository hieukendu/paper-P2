"""E7 reduced BEIR/model representative matrix.

E7 deliberately keeps the same paid-access, mapping, checkpoint and exact
completion primitives as the earlier stages.  The only case-specific input is
the frozen manifest: large BEIR collections use a deterministic 50k-document
background pool and 500 evaluation groups, while small collections reuse their
validated scope.  Query relevance is never used to choose the document pool.
"""

from copy import deepcopy
import gc
import gzip
import json
import resource
from pathlib import Path
import time

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from .config import (freeze_tuning_profile, load_config, load_tuning_profiles,
                     redacted_config, validate_tuning_profile)
from .data.prepare import validate_prepared
from .data.splits import sample_document_pools, stable_key
from .data.store import DocumentStore, RowSubsetDocumentStore
from .encoders import build_encoder, model_specs, resolve_model
from .evaluation import StaticEvaluator
from .experiments import (_completed_prerequisite, finalize_run, hardware_identity,
                           select_map_hyperparameters, source_hash)
from .experiments_e4 import _profile_context as scale_profile_context
from .experiments_e5 import _find_verified_e4_parent
from .hf_sync import snapshot_source
from .io import atomic_bytes, digest, file_digest, read_json, write_json
from .migration import bootstrap_migration, emit_checkpoint, restore_migration, run_migration
from .runtime import cost_scope, probe_hardware, require_target_hardware, target_hardware_matches
from .scheduling import SchedulingTraffic
from .scale_manifest import SCALE_VARIANT, load_common_manifest
from .vectors import PaidEmbeddingAccessor, VectorStore, encode_corpus, encode_query_pool


RUN_BUDGET_POLICY = "compact_v1"
E7_TRAFFIC_SEED = 101
E7_MAP_SEED = 17
E7_DOCUMENT_CAP = 50_000
E7_EVAL_QUERY_CAP = 500
E7_SCHEDULE_QUERY_CAP = 5_000
E7_CALIBRATION_QUERY_CAP = 1_000
E7_TUNE_QUERY_CAP = 2_000
LARGE_CASES = {"nq", "hotpotqa", "fever"}

E7_CASES = (
    ("fiqa", "minilm_mpnet"),
    ("trec-covid", "minilm_mpnet"),
    ("nq", "arctic"),
    ("hotpotqa", "arctic"),
    ("fever", "nomic"),
    ("fiqa", "nomic"),
    ("nq", "bge"),
    ("fever", "bge"),
)
E7_CROSSCHECKS = (
    ("fiqa", "minilm_mpnet"),
    ("nq", "arctic"),
    ("fever", "nomic"),
    ("fever", "bge"),
)


def _peak_rss_bytes():
    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024)


def case_scope(dataset, pair):
    return f"case.{dataset}.{pair}"


def case_manifest_path(root, dataset, pair):
    return (Path(root) / "data" / "processed" / dataset / "manifests" /
            f"e7_{pair}.json")


def _select_role(values, seed, purpose, cap):
    ordered = sorted(set(values), key=lambda value: stable_key(seed, purpose, value))
    return ordered if cap is None else ordered[:cap]


def freeze_case_manifest(dataset, pair, cfg, root):
    """Freeze a case manifest before any E7 quality cell is opened."""
    root = Path(root)
    prepared = root / cfg["paths"]["data"] / "processed" / dataset
    data_manifest = validate_prepared(prepared)
    doc_ids = (prepared / "doc_ids.txt").read_text().splitlines()
    roles = read_json(prepared / "splits" / "query_roles.json")["roles"]
    seed = int(cfg["splits"]["master_seed"])
    large = dataset in LARGE_CASES
    ordered_rows = sorted(range(len(doc_ids)), key=lambda row: stable_key(
        seed, f"E7-{dataset}-uniform-documents", doc_ids[row]))
    rows = ordered_rows[:E7_DOCUMENT_CAP] if large else ordered_rows
    caps = {
        "eval": E7_EVAL_QUERY_CAP if large else None,
        "schedule": E7_SCHEDULE_QUERY_CAP if large else None,
        "cal_fit": E7_CALIBRATION_QUERY_CAP if large else None,
        "cal_check": E7_CALIBRATION_QUERY_CAP if large else None,
        "tune": E7_TUNE_QUERY_CAP if large else None,
    }
    selected_roles = {
        role: _select_role(roles.get(role, []), seed,
                           f"E7-{dataset}-{pair}-{role}", caps[role])
        for role in ("eval", "schedule", "cal_fit", "cal_check", "tune")
    }
    if not selected_roles["eval"]:
        raise ValueError(f"E7_MANIFEST_FAILED: {dataset} has no evaluation groups")
    path = case_manifest_path(root, dataset, pair)
    rows_path = path.with_name(path.stem + ".document_rows.npy")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        manifest = read_json(path)
        _validate_case_manifest(manifest, root, cfg)
        if manifest.get("dataset") != dataset or manifest.get("pair") != pair:
            raise ValueError("E7_MANIFEST_IMMUTABLE: existing case manifest has another case")
        return manifest
    rows_array = np.asarray(rows, dtype=np.int64)
    part = rows_path.with_suffix(".part.npy")
    np.save(part, rows_array)
    part.replace(rows_path)
    payload = {
        "variant": SCALE_VARIANT,
        "dataset": dataset,
        "pair": pair,
        "seed": seed,
        "selection_rule": "stable_hash_uniform_background_v1",
        "large_case": large,
        "document_cap": E7_DOCUMENT_CAP if large else len(rows),
        "document_rows": len(rows),
        "document_rows_path": rows_path.name,
        "document_rows_sha256": file_digest(rows_path),
        "document_ids_sha256": digest([doc_ids[int(row)] for row in rows]),
        "data_release_hash": data_manifest["release_hash"],
        "split_hash": data_manifest["split_hash"],
        "query_caps": caps,
        "query_roles": selected_roles,
        "eval_query_count": len(selected_roles["eval"]),
        "background_selection_excludes_qrels": True,
    }
    manifest = {**payload, "manifest_hash": digest(payload)}
    write_json(path, manifest)
    _validate_case_manifest(manifest, root, cfg)
    return manifest


def _validate_case_manifest(manifest, root, cfg):
    expected = digest({key: value for key, value in manifest.items()
                       if key != "manifest_hash"})
    if manifest.get("manifest_hash") != expected:
        raise ValueError("E7_MANIFEST_INVALID: manifest hash mismatch")
    if manifest.get("variant") != SCALE_VARIANT or not manifest.get("background_selection_excludes_qrels"):
        raise ValueError("E7_MANIFEST_INVALID: scale or selection policy mismatch")
    dataset = manifest.get("dataset")
    prepared = Path(root) / cfg["paths"]["data"] / "processed" / dataset
    data_manifest = validate_prepared(prepared)
    if data_manifest["release_hash"] != manifest.get("data_release_hash"):
        raise ValueError("E7_MANIFEST_INVALID: data release changed")
    if data_manifest["split_hash"] != manifest.get("split_hash"):
        raise ValueError("E7_MANIFEST_INVALID: split hash changed")
    rows_path = Path(manifest.get("document_rows_path", ""))
    rows_path = prepared / "manifests" / rows_path.name
    if not rows_path.is_file() or file_digest(rows_path) != manifest.get("document_rows_sha256"):
        raise ValueError("E7_MANIFEST_INVALID: document row artifact changed")
    rows = np.asarray(np.load(rows_path, allow_pickle=False), dtype=np.int64)
    doc_ids = (prepared / "doc_ids.txt").read_text().splitlines()
    if len(rows) != manifest.get("document_rows") or len(set(rows.tolist())) != len(rows):
        raise ValueError("E7_MANIFEST_INVALID: document rows are not unique")
    if any(row < 0 or row >= len(doc_ids) for row in rows):
        raise ValueError("E7_MANIFEST_INVALID: document row is outside corpus")
    if digest([doc_ids[int(row)] for row in rows]) != manifest.get("document_ids_sha256"):
        raise ValueError("E7_MANIFEST_INVALID: document IDs differ")
    if manifest.get("large_case") and len(rows) != E7_DOCUMENT_CAP:
        raise ValueError("E7_MANIFEST_INVALID: large case is not capped at 50k")
    return rows


def load_case_manifest(cfg, root):
    configured = cfg["experiment"].get("case_manifest_path")
    if not configured:
        raise ValueError("E7_MANIFEST_REQUIRED: case_manifest_path is missing")
    path = Path(root) / configured
    if not path.exists():
        raise ValueError("E7_MANIFEST_REQUIRED: case manifest is missing")
    manifest = read_json(path)
    rows = _validate_case_manifest(manifest, root, cfg)
    if cfg["experiment"].get("case_manifest_hash") != manifest["manifest_hash"]:
        raise ValueError("E7_MANIFEST_REQUIRED: config does not pin case manifest")
    return manifest, rows, path


def _case_inputs(cfg, root, manifest, specs, environment):
    dataset = cfg["dataset"]["name"]
    return {
        "dataset": dataset,
        "release": manifest["data_release_hash"],
        "split_hash": manifest["split_hash"],
        "pair": cfg["models"]["pair"],
        "case_manifest_hash": manifest["manifest_hash"],
        "models": {role: {key: value for key, value in spec.items() if key != "snapshot"}
                    for role, spec in specs.items()},
        "hardware": hardware_identity(environment),
    }


def _case_vector_store(prepared, rows, manifest, spec, cfg, root, role, timing):
    key = digest({"case_manifest": manifest["manifest_hash"],
                  "model": {k: v for k, v in spec.items() if k != "snapshot"},
                  "role": role})
    output = Path(cfg["paths"]["cache"]) / "vectors" / "e7" / (
        f"{manifest['dataset']}-{cfg['models']['pair']}-{role}-{key[:16]}")
    if (output / "manifest.json").exists():
        return VectorStore(output, key), {"cache_hit": True, "cache_key": key}
    store = RowSubsetDocumentStore(DocumentStore(prepared), rows)
    started = time.monotonic()
    encoder = build_encoder(spec, cfg["execution"]["device"], cfg["models"]["batch_size"])
    try:
        result = encode_corpus(store, encoder, output, key)
        cost = dict(encoder.cost)
    finally:
        encoder.close()
    timing.append({"component": f"encode_{role}_case_pool", "wall_seconds": time.monotonic() - started,
                   "source": "measured", "rows": len(rows), "cache_hit": False,
                   "encoder_cost": cost})
    return result, {"cache_hit": False, "cache_key": key, "encoder_cost": cost}


def _query_records(prepared, wanted):
    wanted = set(wanted)
    records = {}
    for batch in pq.ParquetFile(prepared / "queries.parquet").iter_batches(
            columns=["group_id", "text"], batch_size=100_000):
        values = batch.to_pydict()
        for group_id, text in zip(values["group_id"], values["text"]):
            if group_id in wanted:
                records[group_id] = text
        if len(records) == len(wanted):
            break
    missing = wanted - set(records)
    if missing:
        raise ValueError(f"E7_QUERY_GATE_FAILED: {len(missing)} frozen groups are missing")
    return records


def _encode_queries(cfg, root, manifest, records, ids, spec, role, timing):
    if not ids:
        return np.empty((0, spec["dim"]), dtype=np.float32), {"cache_hit": True, "rows": 0}
    output = (Path(cfg["paths"]["cache"]) / "e7" / "queries" /
              f"{manifest['dataset']}-{cfg['models']['pair']}-{role}")
    started = time.monotonic()
    values, meta = encode_query_pool(ids, [records[qid] for qid in ids], spec, cfg, output)
    timing.append({"component": f"encode_{role}_queries", "wall_seconds": time.monotonic() - started,
                   "source": "measured", "rows": len(ids), "cache_hit": meta.get("cache_hit", False)})
    return np.asarray(values), meta


def _read_qrels(prepared, eval_ids, base_rows, local_ids):
    wanted = set(eval_ids)
    row_map = {int(base): local for local, base in enumerate(base_rows.tolist())}
    qrels = {qid: {} for qid in eval_ids}
    for batch in pq.ParquetFile(prepared / "qrels.parquet").iter_batches(
            columns=["split", "group_id", "doc_id", "doc_row", "grade"], batch_size=100_000):
        values = batch.to_pydict()
        for split, group_id, doc_id, doc_row, grade in zip(
                values["split"], values["group_id"], values["doc_id"],
                values["doc_row"], values["grade"]):
            if split != "test" or group_id not in wanted or int(doc_row) not in row_map:
                continue
            local = row_map[int(doc_row)]
            local_id = local_ids[local]
            qrels[group_id][local_id] = max(qrels[group_id].get(local_id, 0), int(grade))
    positive = sum(any(grade > 0 for grade in values.values()) for values in qrels.values())
    return qrels, {"evaluation_queries": len(eval_ids),
                   "queries_with_positive_qrels_in_pool": positive,
                   "coverage": positive / len(eval_ids) if eval_ids else 0.0,
                   "pool_rows": len(base_rows)}


def _schedule_traffic(prepared, manifest, records, schedule_ids, new_queries, base_rows, local_ids):
    if not schedule_ids:
        return None, {"status": "N/A_NO_SCHEDULE_SPLIT", "groups": 0, "groups_with_edges": 0}
    wanted = set(schedule_ids)
    row_map = {int(base): local for local, base in enumerate(base_rows.tolist())}
    proxies = {qid: set() for qid in schedule_ids}
    for batch in pq.ParquetFile(prepared / "qrels.parquet").iter_batches(
            columns=["split", "group_id", "doc_row"], batch_size=100_000):
        values = batch.to_pydict()
        for split, group_id, doc_row in zip(values["split"], values["group_id"], values["doc_row"]):
            if split == "train" and group_id in wanted and int(doc_row) in row_map:
                proxies[group_id].add(row_map[int(doc_row)])
    traffic = SchedulingTraffic(tuple(schedule_ids), new_queries,
                                [proxies[qid] for qid in schedule_ids])
    return traffic, {"status": "MEASURED_STATIC_TRAIN_QRELS", "groups": len(schedule_ids),
                     "groups_with_edges": sum(bool(values) for values in proxies.values())}


def run_case_presetup(task, cfg):
    """Create a case-scoped T0 profile for an E7 representative case."""
    root = Path(task["root"])
    cfg = deepcopy(cfg)
    cfg["execution"]["mode"] = "live_encode"
    scope = cfg["tuning"]["scope"]
    dataset, pair = cfg["dataset"]["name"], cfg["models"]["pair"]
    if scope != case_scope(dataset, pair):
        raise ValueError("T0.case scope does not match dataset/model pair")
    manifest, rows, manifest_file = load_case_manifest(cfg, root)
    environment = probe_hardware()
    require_target_hardware(cfg, environment)
    prepared = root / cfg["paths"]["data"] / "processed" / dataset
    data_manifest = validate_prepared(prepared)
    smoke_path = root / cfg["paths"]["state"] / f"model-smoke-{dataset}-{pair}.json"
    if not smoke_path.exists():
        raise ValueError("MODEL_SMOKE_REQUIRED: case smoke is missing")
    specs = {role: resolve_model(spec, cfg["paths"], root)
             for role, spec in model_specs(pair, root).items()}
    smoke = read_json(smoke_path)
    for role, spec in specs.items():
        if (smoke.get(role, {}).get("revision") != spec["resolved_revision"] or
                smoke.get(role, {}).get("smoke", {}).get("status") != "PASS"):
            raise ValueError("MODEL_SMOKE_REQUIRED: case smoke does not match pinned revisions")
    runtime_dir = _completed_prerequisite(cfg, root, "RUNTIME_PROBE", data_manifest["release_hash"], pair)
    runtime_probe = read_json(runtime_dir / "throughput_probe.json")
    batches = {role: int(runtime_probe["results"][role]["selected_batch_size"])
               for role in ("old", "new")}
    cfg["models"]["batch_size"] = batches["new"]
    refs = _case_inputs(cfg, root, manifest, specs, environment)
    locked = {"source_hash": source_hash(root), "config": redacted_config(cfg),
              "input_refs": refs, "data_release": data_manifest["release_hash"],
              "scope": scope, "runtime_probe": runtime_dir.name,
              "runtime_probe_hash": file_digest(runtime_dir / "throughput_probe.json")}
    label = scope.replace("case.", "").replace("/", "-")
    run_dir = Path(cfg["paths"]["runs"]) / f"T0-case-{label}-{digest(locked)[:12]}"
    run_dir.mkdir(parents=True, exist_ok=True)
    if (run_dir / "summary.json").exists():
        return finalize_run(run_dir, read_json(run_dir / "summary.json"), cfg, root)
    write_json(run_dir / "config.lock.json", locked)
    write_json(run_dir / "dataset_manifest.json", data_manifest)
    write_json(run_dir / "case_manifest.json", manifest)
    write_json(run_dir / "environment.json", environment)
    write_json(run_dir / "models.lock.json", {
        role: {key: value for key, value in spec.items() if key != "snapshot"}
        for role, spec in specs.items()})
    snapshot_source(root, run_dir)
    timing = []
    summary = {"compute_status": "FAILED", "phase": "development", "outcome": "diagnostic",
               "case_scope": scope, "case_manifest_hash": manifest["manifest_hash"],
               "target_hardware_pass": target_hardware_matches(cfg, environment),
               "performance_claim": False, "exclusive": "unverified"}
    new_encoder = None
    try:
        base_store = DocumentStore(prepared)
        old_store, old_meta = _case_vector_store(
            prepared, rows, manifest, specs["old"], cfg, root, "old", timing)
        old = old_store.get_rows(np.arange(len(rows), dtype=np.int64))
        # Materialize the validated corpus IDs once.  Re-reading the complete
        # multi-million-row doc_ids.txt inside the 50k-row comprehension turns
        # this setup into an accidental O(subset * corpus) scan.
        all_doc_ids = (prepared / "doc_ids.txt").read_text().splitlines()
        case_doc_ids = [all_doc_ids[int(row)] for row in rows]
        pools = sample_document_pools(case_doc_ids, cfg)
        new_encoder = build_encoder(specs["new"], cfg["execution"]["device"], batches["new"])

        def live_source(requested):
            documents = RowSubsetDocumentStore(base_store, rows).base.get_documents(
                [int(rows[int(row)]) for row in requested])
            return new_encoder.encode_documents([document.text for document in documents])

        accessor = PaidEmbeddingAccessor(
            live_source,
            {"train": pools["train"], "validation": pools["validation"],
             "backfill": set(range(len(rows))) - set(map(int, pools["train"])) -
             set(map(int, pools["validation"]))},
            len(rows), mode="live_encode", journal=run_dir / "access-journal.json")
        cap = len(pools["train"]) + len(pools["validation"]) + 2 * pools["cal_cap"]
        with cost_scope("case_paid_train_validation_encode", timing):
            y_train = accessor.request(pools["train"], "train", cap)
            y_val = accessor.request(pools["validation"], "validation", cap)
        with cost_scope("case_validation_lr_grid", timing):
            selected, table = select_map_hyperparameters(
                (old[pools["train"]], y_train), (old[pools["validation"]], y_val), cfg)
        pq.write_table(pa.Table.from_pylist(table), run_dir / "selection.parquet")
        candidate = deepcopy(cfg)
        candidate["mapping"]["kind"] = "op"
        candidate["search"]["backend"] = "exact"
        with cost_scope("case_bootstrap_op", timing):
            state = bootstrap_migration(
                doc_ids=case_doc_ids,
                pools=pools, old_vectors=old, paid_accessor=accessor, cfg=candidate)
        checkpoint = emit_checkpoint(state, run_dir / "checkpoints", "bootstrap-op", digest(locked))
        restored_accessor = PaidEmbeddingAccessor(
            lambda requested: old_store.get_rows(requested), accessor.roles, len(rows),
            mode="cached_access")
        restored = restore_migration(checkpoint, old, restored_accessor, candidate, digest(locked))
        restored_pass = (np.array_equal(state.index.vectors, restored.index.vectors) and
                         np.array_equal(state.index.search(state.index.vectors[:8]).rows,
                                        restored.index.search(state.index.vectors[:8]).rows))
        if not restored_pass:
            raise ValueError("T0_CASE_RESTORE_FAILED: bootstrap restore differs")
        write_json(run_dir / "timing.json", {"records": timing,
                   "old_encoder": old_meta, "new_encoder": dict(new_encoder.cost),
                   "runtime_probe": runtime_dir.name, "performance_claim": False,
                   "exclusive": "unverified"})
        write_json(run_dir / "estimate.json", {
            "scope": scope, "case_manifest_hash": manifest["manifest_hash"],
            "required_cells": 3, "runtime": "measured_probe",
            "official_quality": "unmeasured", "performance_claim": False,
            "concurrency": 1})
        selections = {
            "map": selected,
            "search": {"status": "N/A_EXACT", "backend": "exact", "candidates": None,
                        "ef_search": None},
            "ann_status": "N/A_EXACT",
            "runtime": {"batches": batches, "threads": {"selected_threads": cfg["search"]["threads"]},
                        "probe_run": runtime_dir.name},
            "correctness_pass": True, "local_restore_pass": True,
            "target_hardware_pass": target_hardware_matches(cfg, environment),
            "timing_ref": f"{run_dir.name}/timing.json",
            "estimate_ref": f"{run_dir.name}/estimate.json",
            "source_run": run_dir.name, "lr_selection": cfg["tuning"]["policy_version"],
            "case_manifest_hash": manifest["manifest_hash"],
            "case_manifest_path": str(manifest_file.relative_to(root)),
        }
        if source_hash(root) != locked["source_hash"]:
            raise ValueError("SOURCE_CHANGED_DURING_RUN")
        profile_hash = freeze_tuning_profile(scope, selections, refs, cfg, root)
        write_json(run_dir / "tuning_profile.json", {"profile_hash": profile_hash,
                   "scope": scope, "selections": selections, "inputs": refs})
        np.savez(run_dir / "accessed_ids.npz", train=pools["train"], validation=pools["validation"],
                 paid=np.asarray(accessor.order, dtype=np.int64))
        summary.update(compute_status="COMPUTE_DONE", profile_hash=profile_hash,
                       local_restore="PASS", correctness_gate="PASS", documents=len(rows),
                       paid_documents=len(accessor.paid), ann_status="N/A_EXACT",
                       map_selection=selected)
    except Exception as exc:
        summary.update(error_type=type(exc).__name__, reason=str(exc))
        if not (run_dir / "timing.json").exists():
            write_json(run_dir / "timing.json", {"records": timing, "performance_claim": False})
    finally:
        if new_encoder is not None:
            new_encoder.close()
    return finalize_run(run_dir, summary, cfg, root)


def _scale_parent(cfg, root):
    profiles = load_tuning_profiles(root / cfg["tuning"]["lock_path"])
    entries = [(key, value) for key, value in profiles["profiles"].items()
               if value.get("scope") == "scale"]
    if len(entries) != 1:
        raise ValueError("E7_PARENT_REQUIRED: exactly one scale profile is required")
    profile_hash, profile = entries[0]
    scale_cfg = load_config("configs/experiments/e4.yaml", root=root)
    scale_cfg["experiment"].update(profile_hash=profile_hash, tuning_scope="scale",
                                     scale_variant=SCALE_VARIANT)
    manifest = load_common_manifest(scale_cfg, root, profile["selections"]["source_run"])
    scale_cfg["experiment"]["scale_manifest_hash"] = manifest["manifest_hash"]
    scale_cfg["experiment"]["scale_manifest_path"] = str(
        Path(manifest["path"]).relative_to(root))
    context = scale_profile_context(scale_cfg, root, ann_parent_verified=True)
    parent = _find_verified_e4_parent(scale_cfg, root, context)
    return {"profile_hash": profile_hash, "profile": profile, "manifest": manifest,
            "context": context, "parent": parent}


def _load_profile(cfg, root):
    profiles = load_tuning_profiles(root / cfg["tuning"]["lock_path"])
    profile_hash = cfg["experiment"].get("profile_hash")
    profile = profiles["profiles"].get(profile_hash)
    if profile is None or profile.get("scope") != cfg["experiment"].get("tuning_scope"):
        raise ValueError("E7_PROFILE_REQUIRED: case-scoped profile is missing")
    validate_tuning_profile({"phase": "official", "profile_hash": profile_hash,
                             "tuning_scope": profile["scope"], "input_refs": profile["inputs"],
                             "variant_id": "primary", "overrides": {}}, cfg, profiles)
    return profile_hash, profile


def _run_id(cfg, locked):
    case = f"{cfg['dataset']['name']}-{cfg['models']['pair']}"
    scheduler = cfg["scheduler"]["kind"]
    method = cfg["mapping"]["kind"]
    return (f"E7-{case}-{method}-{scheduler}-m{cfg['experiment']['map_seed']}"
            f"-t{cfg['experiment']['traffic_seed']}-{digest(locked)[:12]}")


def run_e7_cell(cfg, root):
    root = Path(root)
    if cfg["execution"]["phase"] != "official" or cfg["execution"]["mode"] != "cached_access":
        raise ValueError("E7 cells require official/cached_access")
    require_target_hardware(cfg, probe_hardware())
    dataset, pair = cfg["dataset"]["name"], cfg["models"]["pair"]
    if (dataset, pair) not in E7_CASES:
        raise ValueError("E7_CELL_INVALID: case is outside the compact representative matrix")
    if cfg["experiment"]["map_seed"] != E7_MAP_SEED or cfg["experiment"]["traffic_seed"] != E7_TRAFFIC_SEED:
        raise ValueError("E7_CELL_INVALID: seed is outside the declared compact matrix")
    if cfg["mapping"]["kind"] == "op" and cfg["scheduler"]["kind"] != "greedy":
        raise ValueError("E7_CELL_INVALID: OP is only a greedy cross-check")
    if cfg["mapping"]["kind"] == "residual_mlp" and cfg["scheduler"]["kind"] not in {"random", "greedy"}:
        raise ValueError("E7_CELL_INVALID: MLP scheduler is random or greedy")
    case_manifest, base_rows, manifest_file = load_case_manifest(cfg, root)
    profile_hash, profile = _load_profile(cfg, root)
    parent = _scale_parent(cfg, root)["parent"]
    if profile["inputs"].get("case_manifest_hash") != case_manifest["manifest_hash"]:
        raise ValueError("E7_PROFILE_REQUIRED: profile and case manifest differ")
    runtime = profile["selections"]["runtime"]
    cfg = deepcopy(cfg)
    cfg["models"]["batch_size"] = int(runtime["batches"]["new"])
    cfg["search"]["threads"] = int(runtime["threads"]["selected_threads"])
    prepared = root / cfg["paths"]["data"] / "processed" / dataset
    data_manifest = validate_prepared(prepared)
    specs = {role: resolve_model(spec, cfg["paths"], root)
             for role, spec in model_specs(pair, root).items()}
    environment = probe_hardware()
    locked = {
        "config": redacted_config(cfg), "source_hash": source_hash(root),
        "run_budget_policy": RUN_BUDGET_POLICY, "scale_variant": SCALE_VARIANT,
        "case_scope": case_scope(dataset, pair), "case_manifest_hash": case_manifest["manifest_hash"],
        "case_manifest_path": str(manifest_file.relative_to(root)),
        "profile_hash": profile_hash, "profile_inputs": profile["inputs"],
        "common_scale_manifest_hash": _scale_parent(cfg, root)["manifest"]["manifest_hash"],
        "parent_e4_artifact_id": parent["artifact_id"],
        "parent_e4_artifact_hash": parent["artifact_hash"],
        "dataset_release_hash": data_manifest["release_hash"],
        "dataset": dataset, "pair": pair, "map_seed": E7_MAP_SEED,
        "traffic_seed": E7_TRAFFIC_SEED, "mapping": cfg["mapping"]["kind"],
        "scheduler": cfg["scheduler"]["kind"], "claim_scope": "reduced_scale_pilot",
    }
    run_dir = Path(cfg["paths"]["runs"]) / _run_id(cfg, locked)
    run_dir.mkdir(parents=True, exist_ok=True)
    if (run_dir / "summary.json").exists():
        previous = read_json(run_dir / "summary.json")
        if previous.get("compute_status") == "COMPUTE_DONE":
            return finalize_run(run_dir, previous, cfg, root)
        raise ValueError("Failed E7 cell is preserved; enqueue a new immutable source revision")
    write_json(run_dir / "config.lock.json", locked)
    write_json(run_dir / "environment.json", environment)
    write_json(run_dir / "dataset_manifest.json", data_manifest)
    write_json(run_dir / "case_manifest.json", case_manifest)
    write_json(run_dir / "tuning_profile.json", {"profile_hash": profile_hash, **profile})
    write_json(run_dir / "reference_inputs.json", {
        "dataset": dataset, "pair": pair, "case_manifest_hash": case_manifest["manifest_hash"],
        "common_scale_manifest_hash": locked["common_scale_manifest_hash"],
        "parent_e4_artifact_id": parent["artifact_id"],
        "parent_e4_artifact_hash": parent["artifact_hash"],
        "quality_labels_opened": True, "claim_scope": "reduced_scale_pilot"})
    write_json(run_dir / "models.lock.json", {
        role: {key: value for key, value in spec.items() if key != "snapshot"}
        for role, spec in specs.items()})
    snapshot_source(root, run_dir)
    summary = {
        "compute_status": "FAILED", "phase": "official", "outcome": "inconclusive",
        "expect_classification": "KHỚP", "correctness_gate": "FAIL",
        "quality_gate": "UNMEASURED", "performance_claim": False,
        "run_budget_policy": RUN_BUDGET_POLICY, "scale_variant": SCALE_VARIANT,
        "claim_scope": "reduced_scale_pilot", "dataset": dataset, "model_pair": pair,
        "mapping": cfg["mapping"]["kind"], "scheduler": cfg["scheduler"]["kind"],
        "map_seed": E7_MAP_SEED, "traffic_seed": E7_TRAFFIC_SEED,
        "case_manifest_hash": case_manifest["manifest_hash"],
        "common_scale_manifest_hash": locked["common_scale_manifest_hash"],
        "parent_e4_artifact_id": parent["artifact_id"],
        "parent_e4_artifact_hash": parent["artifact_hash"],
        "official_doc_pool": len(base_rows), "official_eval_query_cap": case_manifest["eval_query_count"],
    }
    timing, events = [], []
    try:
        doc_ids_all = (prepared / "doc_ids.txt").read_text().splitlines()
        doc_ids = [doc_ids_all[int(row)] for row in base_rows]
        old_store, old_meta = _case_vector_store(
            prepared, base_rows, case_manifest, specs["old"], cfg, root, "old", timing)
        new_store, new_meta = _case_vector_store(
            prepared, base_rows, case_manifest, specs["new"], cfg, root, "new", timing)
        old = old_store.get_rows(np.arange(len(base_rows), dtype=np.int64))
        target = new_store.get_rows(np.arange(len(base_rows), dtype=np.int64))
        roles = case_manifest["query_roles"]
        wanted = set(sum((roles.get(role, []) for role in
                          ("eval", "schedule", "cal_fit", "cal_check", "tune")), []))
        records = _query_records(prepared, wanted)
        eval_ids = list(roles["eval"])
        new_eval, new_eval_meta = _encode_queries(
            cfg, root, case_manifest, records, eval_ids, specs["new"], "eval-new", timing)
        old_eval, old_eval_meta = _encode_queries(
            cfg, root, case_manifest, records, eval_ids, specs["old"], "eval-old", timing)
        qrels, coverage = _read_qrels(prepared, eval_ids, base_rows, doc_ids)
        evaluator = StaticEvaluator(target, old, doc_ids, eval_ids, new_eval, old_eval, qrels)
        schedule_ids = list(roles.get("schedule", []))
        new_schedule, _ = _encode_queries(
            cfg, root, case_manifest, records, schedule_ids, specs["new"], "schedule-new", timing)
        traffic, traffic_meta = _schedule_traffic(
            prepared, case_manifest, records, schedule_ids, new_schedule, base_rows, doc_ids)
        cal_ids = {role: list(roles.get(role, [])) for role in ("cal_fit", "cal_check")}
        calibration_queries = {
            role: {qid: vector for qid, vector in zip(
                cal_ids[role], _encode_queries(cfg, root, case_manifest, records,
                                               cal_ids[role], specs["new"], f"{role}-new", timing)[0])}
            for role in cal_ids
        }
        pools = sample_document_pools(doc_ids, cfg)
        candidate = deepcopy(cfg)
        candidate["search"]["backend"] = "exact"
        with cost_scope("e7_bootstrap", timing):
            state = bootstrap_migration(
                doc_ids, pools, old, PaidEmbeddingAccessor(
                    lambda requested: new_store.get_rows(requested),
                    {"train": pools["train"], "validation": pools["validation"],
                     "backfill": set(range(len(doc_ids))) - set(map(int, pools["train"])) -
                     set(map(int, pools["validation"]))},
                    len(doc_ids), mode="cached_access", journal=run_dir / "access-journal.json"),
                candidate, map_seed=E7_MAP_SEED, traffic_seed=E7_TRAFFIC_SEED,
                calibration_queries=calibration_queries)
        retrieval_path = run_dir / "retrieval.trec.gz"
        with gzip.open(retrieval_path, "wt") as retrieval:
            evaluator.evaluate_references(retrieval)
            evaluator.evaluate_snapshot(state.index, len(state.accessor.paid),
                                        len(state.backfilled), retrieval)
            emit_checkpoint(state, run_dir / "checkpoints", "bootstrap", digest(locked))
            for fraction in cfg["budget"]["checkpoints"]:
                target_paid = int(np.floor(float(fraction) * len(doc_ids)))
                if target_paid <= len(state.accessor.paid):
                    continue
                with cost_scope(f"e7_migration_to_{int(fraction * 100)}pct", timing):
                    result = run_migration(state, [target_paid], traffic=traffic)
                events.extend(result["events"])
                evaluator.evaluate_snapshot(state.index, len(state.accessor.paid),
                                            len(state.backfilled), retrieval)
                emit_checkpoint(state, run_dir / "checkpoints",
                                f"accessed-{len(state.accessor.paid):09d}", digest(locked))
        evaluator.verify_completion(state.index)
        if len(state.accessor.paid) != len(doc_ids) or len(set(state.accessor.order)) != len(doc_ids):
            raise ValueError("E7_COMPLETION_FAILED: unique paid budget is incomplete")
        pq.write_table(pa.Table.from_pylist(evaluator.records), run_dir / "metrics.parquet")
        atomic_bytes(run_dir / "events.jsonl", "".join(
            json.dumps(event, sort_keys=True) + "\n" for event in events).encode())
        checkpoint_rows = []
        for label in sorted({row["checkpoint"] for row in evaluator.records
                              if isinstance(row.get("checkpoint"), str) and
                              row["checkpoint"].startswith("accessed-")}):
            values = [row for row in evaluator.records if row.get("checkpoint") == label]
            checkpoint_rows.append({"checkpoint": label, "rows": len(values),
                                   "arr_at_10": float(np.mean([row["arr_at_10"] for row in values])),
                                   "ndcg_at_10": float(np.mean([row["ndcg_at_10"] for row in values])),
                                   "hit_at_10": float(np.mean([row["hit_at_10"] for row in values]))})
        write_json(run_dir / "e7_metrics.json", {
            "dataset": dataset, "pair": pair, "mapping": cfg["mapping"]["kind"],
            "scheduler": cfg["scheduler"]["kind"], "map_seed": E7_MAP_SEED,
            "traffic_seed": E7_TRAFFIC_SEED, "case_manifest_hash": case_manifest["manifest_hash"],
            "qrel_coverage": coverage, "schedule": traffic_meta,
            "checkpoint_metrics": checkpoint_rows, "completion_exact_agreement": 1.0,
            "judged_metrics": "MEASURED" if coverage["coverage"] == 1.0 else "N/A_REDUCED_COVERAGE",
            "quality_labels_opened": True, "performance_claim": False,
        })
        write_json(run_dir / "timing.json", {
            "records": timing, "migration": state.cost_records,
            "accessor": state.accessor.cost, "old_cache": old_meta, "new_cache": new_meta,
            "query_caches": {"new_eval": new_eval_meta, "old_eval": old_eval_meta},
            "peak_rss_bytes": _peak_rss_bytes(), "performance_claim": False,
            "exclusive": "unverified"})
        np.savez(run_dir / "accessed_ids.npz", paid=np.asarray(state.accessor.order),
                 backfilled=np.asarray(state.backfilled), train=pools["train"],
                 validation=pools["validation"])
        summary.update(compute_status="COMPUTE_DONE", correctness_gate="PASS",
                       quality_gate="MEASURED", documents=len(doc_ids),
                       evaluation_queries=len(eval_ids), unique_paid_documents=len(doc_ids),
                       completion_exact_agreement=1.0, checkpoints=len(checkpoint_rows),
                       qrel_coverage=coverage, schedule=traffic_meta,
                       judged_metrics=("MEASURED" if coverage["coverage"] == 1.0
                                       else "N/A_REDUCED_COVERAGE"),
                       target_hardware_pass=True,
                       performance_claim=False,
                       greedy_count=sum(e.get("greedy_count", 0) for e in events),
                       fallback_count=sum(e.get("fallback_count", 0) for e in events))
    except Exception as exc:
        summary.update(error_type=type(exc).__name__, reason=str(exc), correctness_gate="FAIL")
        write_json(run_dir / "timing.json", {"records": timing, "performance_claim": False})
    finally:
        gc.collect()
    return finalize_run(run_dir, summary, cfg, root)


def build_e7_tasks(cfg, root):
    """Build the serial 16+4 compact E7 matrix behind case profiles/E4."""
    root = Path(root)
    if cfg.get("experiment", {}).get("run_budget_policy") != RUN_BUDGET_POLICY:
        raise ValueError("E7 runner requires run_budget_policy=compact_v1")
    parent_info = _scale_parent(cfg, root)
    profiles = load_tuning_profiles(root / cfg["tuning"]["lock_path"])
    profile_entries = {}
    for dataset, pair in E7_CASES:
        manifest = freeze_case_manifest(dataset, pair, cfg, root)
        scope = case_scope(dataset, pair)
        matches = [(key, value) for key, value in profiles["profiles"].items()
                   if value.get("scope") == scope and
                   value.get("inputs", {}).get("case_manifest_hash") == manifest["manifest_hash"]]
        if len(matches) != 1:
            raise ValueError(f"E7_PROFILE_REQUIRED: exactly one profile required for {scope}")
        profile_entries[(dataset, pair)] = (manifest, matches[0][0], matches[0][1])
    # Find the exact verified E4 parent task so no stale v2/full-scale parent is
    # silently substituted in the dependency graph.
    parent_task = parent_info["parent"]["task_id"]
    common = {
        "config": "configs/experiments/e7.yaml", "phase": "official",
        "measurement_mode": "exclusive", "development_hardware": False,
        "run_budget_policy": RUN_BUDGET_POLICY,
        "resources": {"gpu_device": 0, "gpu_memory_gib": 20, "host_ram_gib": 64,
                       "cpu_cores": 8, "disk_scratch_gib": 32, "io_heavy": True},
        "allow_ann_from_verified_parent": True,
    }
    revision = digest({"source": source_hash(root), "parent": parent_info["parent"]["artifact_hash"],
                       "manifest": parent_info["manifest"]["manifest_hash"],
                       "matrix": {"cases": E7_CASES, "crosschecks": E7_CROSSCHECKS}})[:12]
    tasks, previous = [], parent_task
    for dataset, pair in E7_CASES:
        manifest, profile_hash, profile = profile_entries[(dataset, pair)]
        scope = case_scope(dataset, pair)
        case_dependency = f"T0.{scope}"
        for mapping, scheduler, role in (("residual_mlp", "random", "primary"),
                                          ("residual_mlp", "greedy", "primary")):
            task_id = (f"E7.{dataset}.{pair}.{mapping}.{scheduler}.m{E7_MAP_SEED}.t{E7_TRAFFIC_SEED}.{revision}")
            selected_lr = profile["selections"]["map"][mapping].get("lr")
            mapping_override = {"kind": mapping}
            if selected_lr is not None:
                mapping_override["lr"] = selected_lr
            overrides = {"dataset": {"name": dataset, "subset_size": None},
                         "models": {"pair": pair},
                         "mapping": mapping_override, "scheduler": {"kind": scheduler},
                         "experiment": {
                             "profile_hash": profile_hash, "tuning_scope": scope,
                             "run_budget_policy": RUN_BUDGET_POLICY, "cell_role": role,
                             "map_seed": E7_MAP_SEED, "traffic_seed": E7_TRAFFIC_SEED,
                             "scale_variant": SCALE_VARIANT,
                             "scale_manifest_hash": parent_info["manifest"]["manifest_hash"],
                             "scale_manifest_path": str(Path(parent_info["manifest"]["path"]).relative_to(root)),
                             "case_manifest_hash": manifest["manifest_hash"],
                             "case_manifest_path": str(case_manifest_path(root, dataset, pair).relative_to(root)),
                             "case_scope": scope},
                         "search": {"backend": "exact"},
                         "execution": {"mode": "cached_access", "phase": "official"}}
            task = {**common, "task_id": task_id, "experiment": "E7",
                    "config_overrides": overrides,
                    "profile_hash": profile_hash, "tuning_scope": scope,
                    "input_refs": profile["inputs"], "variant_id": "primary", "overrides": {},
                    "depends_on": [previous, case_dependency], "priority": 40,
                    "case_scope": scope, "parent_e4_artifact_id": parent_info["parent"]["artifact_id"],
                    "parent_e4_artifact_hash": parent_info["parent"]["artifact_hash"]}
            tasks.append(task)
            previous = task_id
        if (dataset, pair) in E7_CROSSCHECKS:
            mapping, scheduler, role = "op", "greedy", "crosscheck"
            task_id = (f"E7.{dataset}.{pair}.{mapping}.{scheduler}.m{E7_MAP_SEED}.t{E7_TRAFFIC_SEED}.{revision}")
            selected_lr = profile["selections"]["map"][mapping].get("lr")
            mapping_override = {"kind": mapping}
            if selected_lr is not None:
                mapping_override["lr"] = selected_lr
            overrides = {"dataset": {"name": dataset, "subset_size": None},
                         "models": {"pair": pair}, "mapping": mapping_override,
                         "scheduler": {"kind": scheduler}, "search": {"backend": "exact"},
                         "execution": {"mode": "cached_access", "phase": "official"},
                         "experiment": {
                             "profile_hash": profile_hash, "tuning_scope": scope,
                             "run_budget_policy": RUN_BUDGET_POLICY, "cell_role": role,
                             "map_seed": E7_MAP_SEED, "traffic_seed": E7_TRAFFIC_SEED,
                             "scale_variant": SCALE_VARIANT,
                             "scale_manifest_hash": parent_info["manifest"]["manifest_hash"],
                             "scale_manifest_path": str(Path(parent_info["manifest"]["path"]).relative_to(root)),
                             "case_manifest_hash": manifest["manifest_hash"],
                             "case_manifest_path": str(case_manifest_path(root, dataset, pair).relative_to(root)),
                             "case_scope": scope}}
            tasks.append({**common, "task_id": task_id, "experiment": "E7",
                          "config_overrides": overrides, "profile_hash": profile_hash,
                          "tuning_scope": scope, "input_refs": profile["inputs"],
                          "variant_id": "crosscheck", "overrides": {},
                          "depends_on": [previous, case_dependency], "priority": 35,
                          "case_scope": scope, "parent_e4_artifact_id": parent_info["parent"]["artifact_id"],
                          "parent_e4_artifact_hash": parent_info["parent"]["artifact_hash"]})
            previous = task_id
    from .queue import validate_jobs
    return validate_jobs(tasks)
