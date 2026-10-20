"""Full-corpus static preflight and official cells sharing the migration primitives."""

from copy import deepcopy
from dataclasses import asdict
import gzip
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from .config import load_tuning_profiles, redacted_config, validate_tuning_profile
from .data.prepare import validate_prepared
from .data.splits import sample_document_pools, stable_key
from .data.store import DocumentStore
from .encoders import build_encoder, model_specs, resolve_model
from .evaluation import StaticEvaluator
from .experiments import finalize_run, hardware_identity, source_hash
from .hf_sync import snapshot_source
from .io import atomic_bytes, digest, file_digest, read_json, write_json
from .maps import load_map_state, save_map_state, transform_global
from .migration import bootstrap_migration, emit_checkpoint, restore_migration, run_migration
from .progress import update_checklist
from .runtime import cost_scope, probe_hardware, require_target_hardware
from .scheduling import SchedulingTraffic
from .vectors import PaidEmbeddingAccessor, VectorStore, encode_corpus, encode_query_pool, vector_cache_key


VARIANTS = {
    "global": ("none", False), "global_cal": ("none", True),
    "regional": ("full", False), "primary": ("full", True),
    "diagonal": ("diagonal", True),
}

# The default execution policy is deliberately smaller than the factorial
# paper matrix.  Keep this declaration next to the task builder so a config or
# queue change cannot silently expand the official study again.
RUN_BUDGET_POLICY = "compact_v1"
COMPACT_E2_MAPPING = ("op", "la", "residual_mlp")
COMPACT_E2_SCHEDULERS = ("random", "degree", "read", "greedy")
COMPACT_E2_MAP_SEEDS = (17, 29, 43)
COMPACT_E2_TRAFFIC_SEED = 101


def compact_e2_cell_count():
    return (len(COMPACT_E2_MAPPING) * len(COMPACT_E2_MAP_SEEDS)
            + len(COMPACT_E2_SCHEDULERS) * len(COMPACT_E2_MAP_SEEDS) + len(COMPACT_E2_MAPPING))


def _profile_context(cfg, root):
    profiles = load_tuning_profiles(root / cfg["tuning"]["lock_path"])
    key = cfg["experiment"]["profile_hash"]
    if key not in profiles["profiles"]:
        raise ValueError("TUNING_REQUIRED: specify a frozen profile hash")
    profile = profiles["profiles"][key]
    # Preflight uses the same frozen policy as the subsequent official cell.
    variant = cfg["experiment"]["variant"]
    if variant not in VARIANTS or (cfg["mapping"]["regional"], cfg["calibration"]["enabled"]) != VARIANTS[variant]:
        raise ValueError("Resolved mapping/calibration differs from the declared E2 variant")
    overrides = {} if variant == "primary" else {
        "mapping.regional": cfg["mapping"]["regional"], "calibration.enabled": cfg["calibration"]["enabled"]}
    validate_tuning_profile({"phase": "official", "profile_hash": key,
                             "tuning_scope": profile["scope"], "input_refs": profile["inputs"],
                             "variant_id": variant, "overrides": overrides}, cfg, profiles)
    if (cfg["dataset"]["name"], cfg["models"]["pair"], cfg["dataset"]["subset_size"]) != (
            "fiqa", "minilm_mpnet", None):
        raise ValueError("This runner requires full FiQA/MiniLM-MPNet; other cases need their own scope")
    require_target_hardware(cfg, probe_hardware())
    prepared = Path(cfg["paths"]["data"]) / "processed" / cfg["dataset"]["name"]
    manifest = validate_prepared(prepared)
    specs = {role: resolve_model(spec, cfg["paths"], root)
             for role, spec in model_specs(cfg["models"]["pair"], root).items()}
    refs = {"dataset": cfg["dataset"]["name"], "release": manifest["release_hash"],
            "split_hash": manifest["split_hash"], "pair": cfg["models"]["pair"],
            "models": {role: {k: v for k, v in spec.items() if k != "snapshot"}
                       for role, spec in specs.items()}, "hardware": hardware_identity(probe_hardware())}
    if refs != profile["inputs"]:
        raise ValueError("Frozen profile does not match actual data/model/split/hardware inputs")
    source = Path(cfg["paths"]["runs"]) / profile["selections"]["source_run"]
    previous = read_json(source / "summary.json")
    if previous.get("compute_status") != "COMPUTE_DONE" or previous.get("profile_hash") != key:
        raise ValueError("Frozen profile source run has not completed its gates")
    baseline = read_json(source / "config.lock.json")["config"]
    for section, keys in {"mapping": ("ridge", "min_region_pairs", "region_target_pairs", "region_max"),
                          "scheduler": ("batch_fraction", "refit_fraction", "fallback"),
                          "search": ("M", "ef_construction", "k", "chunk_rows")}.items():
        if any(cfg[section][key] != baseline[section][key] for key in keys):
            raise ValueError("Scientific settings differ from the frozen protocol")
    expected = profile["selections"]["runtime"]
    if cfg["search"]["threads"] != expected["threads"]["selected_threads"]:
        raise ValueError("Worker thread setting differs from frozen runtime profile")
    if cfg["models"]["batch_size"] != expected["batches"]["new"]:
        raise ValueError("Encoder batch size differs from frozen runtime profile")
    return profile, source, prepared, manifest, specs


def _old_vectors(manifest, spec, cfg):
    key = vector_cache_key(manifest, spec, "old_documents")
    store = VectorStore(Path(cfg["paths"]["cache"]) / "vectors" / key, key)
    values = np.empty((store.manifest["rows"], store.manifest["dim"]), dtype=np.float32)
    for start, batch in store.iter_batches():
        values[start:start + len(batch)] = batch
    return values


def _common_bootstrap(source):
    checkpoint = source / "checkpoints/bootstrap-op"
    record = read_json(checkpoint / "checkpoint.json")
    if not record.get("complete"):
        raise ValueError("Common calibration bootstrap is incomplete")
    for name, sha in record["files"].items():
        if file_digest(checkpoint / name) != sha:
            raise ValueError("Common bootstrap checksum mismatch")
    pools = read_json(checkpoint / "calibration_pools.json")
    with np.load(checkpoint / "calibration_queries.npz", allow_pickle=False) as arrays:
        queries = dict(zip(arrays["query_ids"].tolist(), arrays["vectors"]))
    role_queries = {role: {qid: queries[qid] for qid, _ in pool["pairs"]}
                    for role, pool in pools.items()}
    with np.load(checkpoint / "state.npz", allow_pickle=False) as arrays:
        paid = arrays["paid_order"].copy()
    vectors = np.load(checkpoint / "index/vectors.npy", mmap_mode="r", allow_pickle=False)
    return pools, role_queries, {int(row): vectors[row].copy() for row in paid}


def _variant_config(cfg, kind, variant, selected):
    result = deepcopy(cfg)
    result["mapping"].update(kind=kind, regional=VARIANTS[variant][0])
    result["calibration"]["enabled"] = VARIANTS[variant][1]
    if selected[kind]["lr"] is not None:
        result["mapping"]["lr"] = selected[kind]["lr"]
    return result


def _accessor(source, pools, n, journal=None, mode="cached_access"):
    reserved = set(map(int, pools["train"])) | set(map(int, pools["validation"]))
    return PaidEmbeddingAccessor(source, {"train": pools["train"], "validation": pools["validation"],
                                          "backfill": set(range(n)) - reserved}, n, mode, journal)


def _development_traffic(prepared, spec, cfg):
    roles = read_json(prepared / "splits/query_roles.json")["roles"]
    groups = {g["group_id"]: g for g in pq.read_table(prepared / "queries.parquet").to_pylist()}
    order = sorted(roles["schedule"], key=lambda q: stable_key(
        cfg["experiment"]["traffic_seed"], "static-query-order", q))
    if not order or set(order) & set(roles["eval"]):
        raise ValueError("Independent scheduling queries are required")
    values, meta = encode_query_pool(order, [groups[q]["text"] for q in order], spec, cfg,
        Path(cfg["paths"]["cache"]) / "vectors/queries" / digest({"role": "schedule", "ids": order,
        "release": file_digest(prepared / "manifest.json"), "model": spec["resolved_revision"]}))
    proxies = {qid: set() for qid in order}
    # A filtered read never loads test qrels into the scheduling layer.
    for row in pq.read_table(prepared / "qrels.parquet", filters=[("split", "=", "train")],
                              columns=["group_id", "doc_row", "grade"]).to_pylist():
        if row["group_id"] in proxies and row["grade"] > 0:
            proxies[row["group_id"]].add(row["doc_row"])
    return SchedulingTraffic(tuple(order), values, [proxies[q] for q in order]), meta


def run_static_preflight(cfg, root):
    """Check all declared exact E2 map/variant/seeds before opening test results."""
    root = Path(root)
    profile, source, prepared, manifest, specs = _profile_context(cfg, root)
    cfg = deepcopy(cfg)
    cfg["execution"]["phase"] = "development"
    if cfg["search"]["backend"] != "exact":
        raise ValueError("This preflight certifies exact E2 only; ANN variants require a separate preflight")
    locked = {"config": redacted_config(cfg), "source_hash": source_hash(root),
              "profile_hash": cfg["experiment"]["profile_hash"], "input_refs": profile["inputs"],
              "run_budget_policy": RUN_BUDGET_POLICY,
              "comparison_variants": {"primary": list(VARIANTS["primary"])}}
    run_dir = Path(cfg["paths"]["runs"]) / f"E2_PREFLIGHT-fiqa-{digest(locked)[:12]}"
    run_dir.mkdir(parents=True, exist_ok=True)
    if (run_dir / "summary.json").exists():
        return finalize_run(run_dir, read_json(run_dir / "summary.json"), cfg, root)
    write_json(run_dir / "config.lock.json", locked)
    write_json(run_dir / "dataset_manifest.json", manifest)
    write_json(run_dir / "environment.json", probe_hardware())
    write_json(run_dir / "tuning_profile.json", {"profile_hash": cfg["experiment"]["profile_hash"], **profile})
    snapshot_source(root, run_dir)
    update_checklist(root, run_dir.name, {"compute_status": "RUNNING", "outcome": "diagnostic"})
    summary = {"compute_status": "FAILED", "phase": "development", "outcome": "diagnostic",
               "test_results_opened": False, "search_backend": "exact", "performance_claim": False}
    encoder, timings, rows = None, [], []
    try:
        old = _old_vectors(manifest, specs["old"], cfg)
        doc_ids = (prepared / "doc_ids.txt").read_text().splitlines()
        n = len(doc_ids)
        pools = sample_document_pools(doc_ids, cfg)
        fixed, calibration, paid = _common_bootstrap(source)
        def paid_only(ids):
            if any(int(row) not in paid for row in ids):
                raise PermissionError("Preflight bootstrap requested an unpaid target")
            return np.stack([paid[int(row)] for row in ids])
        selected = profile["selections"]["map"]
        for seed in COMPACT_E2_MAP_SEEDS:
            for kind in COMPACT_E2_MAPPING:
                variant = "primary"
                candidate = _variant_config(cfg, kind, variant, selected)
                with cost_scope("bootstrap_and_map_restore", timings) as record:
                    state = bootstrap_migration(doc_ids, pools, old, _accessor(paid_only, pools, n),
                        candidate, map_seed=seed, calibration_queries=calibration,
                        fixed_calibration_pools=fixed)
                    path = run_dir / "checkpoints" / f"{kind}-{variant}-{seed}"
                    path.mkdir(parents=True)
                    save_map_state(state.M0, path / "M0.safetensors")
                    restored_map = load_map_state(path / "M0.safetensors")
                    if not np.array_equal(transform_global(state.M0, old[:16]),
                                          transform_global(restored_map, old[:16])):
                        raise ValueError("Map round-trip differs during seed preflight")
                    if set(state.accessor.paid) != set(paid):
                        raise ValueError("Variant changed the common bootstrap document budget")
                    for ids in (pools["validation"], fixed["cal_fit"]["rows"], fixed["cal_check"]["rows"]):
                        if set(map(int, ids)) & state.statistics.seen:
                            raise PermissionError("Held-out document entered preflight regional fitting")
                    write_json(path / "checkpoint.json", {"complete": True, "map_only": True,
                        "files": {"M0.safetensors": file_digest(path / "M0.safetensors")}})
                    record.update(map_kind=kind, variant=variant, map_seed=seed)
                    rows.append({"kind": kind, "variant": variant, "map_seed": seed,
                                 "status": "PASS", "paid_documents": len(state.accessor.paid),
                                 "calibration_reason": state.index.calibration.reason})
                print(f"E2 preflight: {kind}/{variant}/seed{seed} PASS", flush=True)
                del state, restored_map
        # Predetermined greedy-only development timing; no test query or relevance is read.
        traffic, traffic_meta = _development_traffic(prepared, specs["new"], cfg)
        store = DocumentStore(prepared)
        encoder = build_encoder(specs["new"], cfg["execution"]["device"], cfg["models"]["batch_size"])
        def probe_source(ids):
            missing = [int(row) for row in ids if int(row) not in paid]
            if missing:
                encoded = encoder.encode_documents([d.text for d in store.get_documents(missing)])
                paid.update(zip(missing, encoded))
            return np.stack([paid[int(row)] for row in ids])
        probe_cfg = _variant_config(cfg, "residual_mlp", "primary", selected)
        probe_cfg["scheduler"]["kind"] = "greedy"
        state = bootstrap_migration(doc_ids, pools, old, _accessor(probe_source, pools, n, mode="live_encode"),
            probe_cfg, calibration_queries=calibration, fixed_calibration_pools=fixed)
        initial = len(state.accessor.paid)
        with cost_scope("greedy_development_to_10pct", timings):
            primary = run_migration(state, [int(.1 * n)], traffic=traffic)
        with cost_scope("greedy_development_10_to_25pct", timings):
            continued = run_migration(state, [int(.25 * n)], traffic=traffic)
        result = {"events": primary["events"] + continued["events"]}
        path = emit_checkpoint(state, run_dir / "checkpoints", "development-25pct", digest(locked))
        restored = restore_migration(path, old, _accessor(probe_source, pools, n), probe_cfg, digest(locked))
        if (restored.backfilled != state.backfilled or
                not np.array_equal(restored.index.vectors, state.index.vectors)):
            raise ValueError("Development migration restore failed")
        pq.write_table(pa.Table.from_pylist(rows), run_dir / "selection.parquet")
        write_json(run_dir / "timing.json", {"records": timings, "migration": state.cost_records,
            "encoder": encoder.cost, "query_cache": traffic_meta, "performance_claim": False,
            "bootstrap_cache_reused": True, "exclusive": "unverified"})
        primary_seconds = timings[-2]["wall_seconds"]
        continuation_seconds = timings[-1]["wall_seconds"]
        # This is an observed same-corpus probe, with search and remap already included.
        write_json(run_dir / "estimate.json", {"scope": "FiQA exact E2",
            "measured_development_primary_seconds": primary_seconds,
            "measured_development_10_to_25pct_seconds": continuation_seconds,
            "forecast_full_cell": {"kind": "unmeasured", "reason": "100% continuation not timed yet"},
            "forecast_primary_migration": {"kind": "estimated", "seconds": primary_seconds,
                "source": "timing.json:greedy_development_to_10pct", "note": "same-case prefix, shared host"},
            "matrix_cells": compact_e2_cell_count(), "run_budget_policy": RUN_BUDGET_POLICY,
            "concurrency": 1, "performance_claim": False})
        if source_hash(root) != locked["source_hash"]:
            raise ValueError("SOURCE_CHANGED_DURING_RUN")
        summary.update(compute_status="COMPUTE_DONE", checked_cells=len(rows),
            profile_hash=cfg["experiment"]["profile_hash"], bootstrap_paid=initial,
            development_paid=len(state.accessor.paid), local_restore="PASS",
            variants=["primary"], map_seeds=list(COMPACT_E2_MAP_SEEDS),
            run_budget_policy=RUN_BUDGET_POLICY,
            greedy_count=sum(e["greedy_count"] for e in result["events"]),
            fallback_count=sum(e["fallback_count"] for e in result["events"]))
    except Exception as exc:
        summary.update(error_type=type(exc).__name__,
                       reason=str(exc) if isinstance(exc, (ValueError, PermissionError)) else "See local worker log")
        write_json(run_dir / "timing.json", {"records": timings, "performance_claim": False})
    finally:
        if encoder is not None:
            encoder.close()
    return finalize_run(run_dir, summary, cfg, root)


def _preflight_for_cell(cfg, root, profile):
    identifier = cfg["experiment"]["preflight_run"]
    if not identifier or Path(identifier).name != identifier:
        raise ValueError("E2_PREFLIGHT_REQUIRED: specify the completed exact comparison preflight")
    path = Path(cfg["paths"]["runs"]) / identifier
    summary, locked = read_json(path / "summary.json"), read_json(path / "config.lock.json")
    if (summary.get("compute_status") != "COMPUTE_DONE" or
            summary.get("profile_hash") != cfg["experiment"]["profile_hash"] or
            locked.get("input_refs") != profile["inputs"] or
            locked.get("source_hash") != source_hash(root) or
            summary.get("checked_cells") != len(COMPACT_E2_MAPPING) * len(COMPACT_E2_MAP_SEEDS) or
            summary.get("map_seeds") != list(COMPACT_E2_MAP_SEEDS) or
            summary.get("variants") != ["primary"] or
            summary.get("run_budget_policy") != RUN_BUDGET_POLICY):
        raise ValueError("E2_PREFLIGHT_REQUIRED: exact comparison source/inputs/variants/seeds differ")
    return path


def _build_evaluator(prepared, manifest, specs, old, cfg, run_dir, timing):
    roles = read_json(prepared / "splits/query_roles.json")["roles"]
    groups = {g["group_id"]: g for g in pq.read_table(prepared / "queries.parquet").to_pylist()}
    ids = (prepared / "doc_ids.txt").read_text().splitlines()
    eval_ids = sorted(roles["eval"])
    texts = [groups[q]["text"] for q in eval_ids]
    cache = Path(cfg["paths"]["cache"])
    query_vectors, references = {}, {}
    for role in ("old", "new"):
        with cost_scope(f"research_{role}_eval_query_cache", timing):
            spec = specs[role]
            query_cfg = deepcopy(cfg)
            query_vectors[role], meta = encode_query_pool(eval_ids, texts, spec, query_cfg,
                cache / "evaluator/queries" / digest({"ids": eval_ids, "model": spec["repo_id"],
                    "revision": spec["resolved_revision"], "release": manifest["release_hash"]}))
            references[role + "_query_cache"] = meta["cache_key"]
    encoder = build_encoder(specs["new"], cfg["execution"]["device"], cfg["models"]["batch_size"])
    try:
        key = vector_cache_key(manifest, specs["new"], "evaluator_documents")
        existed = (cache / "evaluator" / key / "manifest.json").exists()
        with cost_scope("research_full_new_encode_or_cache", timing) as record:
            store = encode_corpus(DocumentStore(prepared), encoder, cache / "evaluator" / key, key)
            target = np.empty((len(ids), specs["new"]["dim"]), dtype=np.float32)
            for start, values in store.iter_batches():
                target[start:start + len(values)] = values
            record["cache_hit"] = existed
    finally:
        encoder.close()
    qrels = {qid: {} for qid in eval_ids}
    for row in pq.read_table(prepared / "qrels.parquet", filters=[("split", "=", "test")]).to_pylist():
        if row["group_id"] in qrels:
            group = qrels[row["group_id"]]
            group[row["doc_id"]] = max(group.get(row["doc_id"], 0), row["grade"])
    write_json(run_dir / "reference_inputs.json", {"target_cache_key": key, **references,
        "encoder_original_cache_cost": store.manifest["encoder_cost"],
        "cost_scope": "evaluator/research, excluded from migration GPU-time claims",
        "query_groups": eval_ids, "ranking_score": "negative rank, not cosine"})
    with cost_scope("research_exact_references", timing):
        return StaticEvaluator(target, old, ids, eval_ids, query_vectors["new"], query_vectors["old"], qrels)


def run_static_cell(cfg, root):
    """Execute one full FiQA exact E2 cell after immutable profile/preflight gates."""
    root = Path(root)
    if cfg["execution"]["phase"] != "official" or cfg["execution"]["mode"] != "cached_access":
        raise ValueError("Official quality cells require official/cached_access with explicit research costs")
    if cfg["search"]["backend"] != "exact":
        raise ValueError("E2 starts exact; ANN experiment execution requires a separate comparison preflight")
    profile, source, prepared, manifest, specs = _profile_context(cfg, root)
    preflight = _preflight_for_cell(cfg, root, profile)
    seeds = cfg["experiment"]
    cell_role = seeds.get("cell_role", "legacy")
    locked = {"config": redacted_config(cfg), "source_hash": source_hash(root),
              "profile_hash": seeds["profile_hash"], "input_refs": profile["inputs"],
              "run_budget_policy": RUN_BUDGET_POLICY, "cell_role": cell_role,
              "preflight_hash": file_digest(preflight / "summary.json")}
    run_id = (f"E2-fiqa-{cell_role}-{cfg['mapping']['kind']}-{seeds['variant']}-{cfg['scheduler']['kind']}"
              f"-m{seeds['map_seed']}-t{seeds['traffic_seed']}-{digest(locked)[:12]}")
    run_dir = Path(cfg["paths"]["runs"]) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    if (run_dir / "summary.json").exists():
        summary = read_json(run_dir / "summary.json")
        if summary.get("compute_status") == "COMPUTE_DONE":
            return finalize_run(run_dir, summary, cfg, root)
        raise ValueError("Failed official cell is preserved; investigate its checkpoint before resuming")
    write_json(run_dir / "config.lock.json", locked)
    write_json(run_dir / "environment.json", probe_hardware())
    write_json(run_dir / "dataset_manifest.json", manifest)
    write_json(run_dir / "models.lock.json", {r: {k: v for k, v in s.items() if k != "snapshot"}
                                               for r, s in specs.items()})
    write_json(run_dir / "tuning_profile.json", {"profile_hash": seeds["profile_hash"], **profile})
    snapshot_source(root, run_dir)
    update_checklist(root, run_id, {"compute_status": "RUNNING", "phase": "official", "outcome": "inconclusive"})
    print(f"OFFICIAL E2 STARTED: {run_id}", flush=True)
    timing, events = [], []
    summary = {"compute_status": "FAILED", "phase": "official", "outcome": "inconclusive",
               "performance_claim": False, "execution_mode": "cached_access",
               "profile_hash": seeds["profile_hash"], "preflight_run": preflight.name,
               "run_budget_policy": RUN_BUDGET_POLICY, "cell_role": cell_role}
    try:
        old = _old_vectors(manifest, specs["old"], cfg)
        doc_ids = (prepared / "doc_ids.txt").read_text().splitlines()
        n = len(doc_ids)
        pools = sample_document_pools(doc_ids, cfg)
        fixed, calibration, _ = _common_bootstrap(source)
        evaluator = _build_evaluator(prepared, manifest, specs, old, cfg, run_dir, timing)
        traffic = None
        if cfg["scheduler"]["kind"] != "random":
            with cost_scope("migration_scheduling_query_cache", timing):
                traffic, _ = _development_traffic(prepared, specs["new"], cfg)
        accessor = _accessor(evaluator.paid_rows, pools, n, run_dir / "access-journal.json")
        checkpoint_dirs = list((run_dir / "checkpoints").glob("accessed-*"))
        if checkpoint_dirs:
            complete = [p for p in checkpoint_dirs if (p / "checkpoint.json").exists() and
                        read_json(p / "checkpoint.json").get("complete")]
            if not complete:
                raise ValueError("No complete official checkpoint exists to resume")
            latest = max(complete, key=lambda p: read_json(p / "checkpoint.json")["paid"])
            state = restore_migration(latest, old, accessor, cfg, digest(locked))
            evaluator.records = pq.read_table(run_dir / "metrics.parquet").to_pylist()
            import json
            events = [json.loads(line) for line in (run_dir / "events.jsonl").read_text().splitlines()]
            retrieval_mode = "at"
        else:
            if accessor.paid:
                raise ValueError("Paid journal has no complete checkpoint; explicit reconciliation is required")
            with cost_scope("migration_bootstrap", timing):
                state = bootstrap_migration(doc_ids, pools, old, accessor, cfg,
                    map_seed=seeds["map_seed"], traffic_seed=seeds["traffic_seed"],
                    calibration_queries=calibration, fixed_calibration_pools=fixed)
            retrieval_mode = "wt"
        def persist():
            for record in evaluator.records:
                record.update(phase="official", map_seed=seeds["map_seed"], traffic_seed=seeds["traffic_seed"])
            output = run_dir / "metrics.part.parquet"
            pq.write_table(pa.Table.from_pylist(evaluator.records), output)
            output.replace(run_dir / "metrics.parquet")
            import json
            atomic_bytes(run_dir / "events.jsonl", "".join(json.dumps(e) + "\n" for e in events).encode())
        with gzip.open(run_dir / "retrieval.trec.gz", retrieval_mode) as retrieval:
            if not checkpoint_dirs:
                evaluator.evaluate_references(retrieval)
                evaluator.evaluate_snapshot(state.index, len(accessor.paid), len(state.backfilled), retrieval)
                retrieval.flush()
                persist()
                emit_checkpoint(state, run_dir / "checkpoints", f"accessed-{len(accessor.paid):09d}", digest(locked))
            for target in (int(np.floor(f * n)) for f in cfg["budget"]["checkpoints"]):
                if target <= len(accessor.paid):
                    continue
                with cost_scope("migration_to_checkpoint", timing) as timer:
                    result = run_migration(state, [target], traffic=traffic)
                    timer["paid_target"] = target
                events.extend(result["events"])
                with cost_scope("research_checkpoint_evaluation", timing):
                    evaluator.evaluate_snapshot(state.index, len(accessor.paid), len(state.backfilled), retrieval)
                retrieval.flush()
                persist()
                with cost_scope("checkpoint_write", timing):
                    emit_checkpoint(state, run_dir / "checkpoints", f"accessed-{target:09d}", digest(locked))
                print(f"{run_id}: {target}/{n} accessed; exact checkpoint saved", flush=True)
        evaluator.verify_completion(state.index)
        if len(accessor.paid) != n or len(set(accessor.order)) != n:
            raise ValueError("Completed official cell has an incorrect unique paid budget")
        np.savez(run_dir / "accessed_ids.npz", paid=np.array(accessor.order), backfilled=np.array(state.backfilled),
                 train=pools["train"], validation=pools["validation"],
                 cal_fit=fixed["cal_fit"]["rows"], cal_check=fixed["cal_check"]["rows"])
        write_json(run_dir / "timing.json", {"records": timing, "migration": state.cost_records,
            "accessor": accessor.cost, "performance_claim": False, "exclusive": "unverified",
            "encoder_gpu_time": "not measured in cached_access; evaluator encoding is research cost"})
        if source_hash(root) != locked["source_hash"]:
            raise ValueError("SOURCE_CHANGED_DURING_RUN")
        summary.update(compute_status="COMPUTE_DONE", documents=n, evaluation_queries=len(evaluator.query_ids),
            completion_exact_agreement=1., unique_paid_documents=n, checkpoints=len(cfg["budget"]["checkpoints"]) + 1,
            calibration=asdict(state.index.calibration),
            greedy_count=sum(e["greedy_count"] for e in events), fallback_count=sum(e["fallback_count"] for e in events))
    except Exception as exc:
        summary.update(error_type=type(exc).__name__,
                       reason=str(exc) if isinstance(exc, (ValueError, PermissionError)) else "See local worker log")
        write_json(run_dir / "timing.json", {"records": timing, "performance_claim": False})
    return finalize_run(run_dir, summary, cfg, root)


def build_static_tasks(cfg, root):
    """Declare the compact_v1 E2 comparison before test evaluation."""
    root = Path(root)
    if cfg["experiment"].get("run_budget_policy") != RUN_BUDGET_POLICY:
        raise ValueError(f"E2 runner requires run_budget_policy={RUN_BUDGET_POLICY}")
    profile, source, _, _, _ = _profile_context(cfg, root)
    revision = digest({"source": source_hash(root), "config": redacted_config(cfg)})[:12]
    preflight_id = f"E2.exact.preflight.{revision}"
    dependencies = []
    state_path = Path(cfg["paths"]["state"]) / "tasks.json"
    if state_path.exists():
        for identifier, row in read_json(state_path)["tasks"].items():
            if row.get("run_dir") == str(source):
                dependencies.append(identifier)
    if not dependencies:
        raise ValueError("The concrete completed T0 task must be registered before E2 enqueue")
    resources = {"gpu_device": 0, "gpu_memory_gib": 2, "host_ram_gib": 8,
                 "cpu_cores": 8, "disk_scratch_gib": 4, "io_heavy": False}
    common = {"config": "configs/experiments/e2.yaml", "measurement_mode": "quality",
              "resources": resources, "development_hardware": False}
    preflight_cfg = deepcopy(cfg)
    preflight_cfg["execution"]["phase"] = "development"
    preflight = {**common, "task_id": preflight_id, "experiment": "E2_PREFLIGHT",
                 "phase": "development", "config_overrides": preflight_cfg,
                 "depends_on": dependencies, "priority": 100}
    # Preflight ID is deterministic from its resolved config/source, independent of outputs.
    identity = {"config": redacted_config(preflight_cfg), "source_hash": source_hash(root),
                "profile_hash": cfg["experiment"]["profile_hash"], "input_refs": profile["inputs"],
                "run_budget_policy": RUN_BUDGET_POLICY,
                "comparison_variants": {"primary": list(VARIANTS["primary"])}}
    preflight_run = f"E2_PREFLIGHT-fiqa-{digest(identity)[:12]}"
    mapping_specs = [(kind, "primary", "random", seed, COMPACT_E2_TRAFFIC_SEED, "mapping")
                     for kind in COMPACT_E2_MAPPING for seed in COMPACT_E2_MAP_SEEDS]
    scheduler_specs = [("residual_mlp", "primary", scheduler, seed, COMPACT_E2_TRAFFIC_SEED, "scheduler")
                       for scheduler in COMPACT_E2_SCHEDULERS for seed in COMPACT_E2_MAP_SEEDS]
    # TREC is a required compact cell family, but its scoped T0.case profile is
    # intentionally a separate dependency.  The tasks remain pending until
    # that profile exists; no FiQA profile is silently transferred to TREC.
    trec_specs = [(kind, "primary", "random", 17, COMPACT_E2_TRAFFIC_SEED, "mapping")
                  for kind in COMPACT_E2_MAPPING]
    tasks = [preflight]
    mapping_ids, scheduler_ids = [], []
    for kind, variant, scheduler, seed, traffic_seed, cell_role, is_trec in (
            [(kind, variant, scheduler, seed, traffic_seed, role, False)
             for kind, variant, scheduler, seed, traffic_seed, role in mapping_specs + scheduler_specs]
            + [(kind, variant, scheduler, seed, traffic_seed, role, True)
               for kind, variant, scheduler, seed, traffic_seed, role in trec_specs]):
        resolved = _variant_config(cfg, kind, variant, profile["selections"]["map"])
        resolved["scheduler"]["kind"] = scheduler
        resolved["experiment"].update(variant=variant, map_seed=seed, traffic_seed=traffic_seed,
                                       cell_role=cell_role,
                                       preflight_run=preflight_run)
        if is_trec:
            resolved["dataset"]["name"] = "trec-covid"
            resolved["experiment"]["profile_hash"] = None
        dataset_tag = "trec" if is_trec else "fiqa"
        task_id = f"E2.{dataset_tag}.{cell_role}.{kind}.{variant}.{scheduler}.m{seed}.t{traffic_seed}.{revision}"
        overrides = {} if variant == "primary" else {
            "mapping.regional": resolved["mapping"]["regional"],
            "calibration.enabled": resolved["calibration"]["enabled"]}
        depends = [preflight_id]
        if is_trec:
            depends.extend(scheduler_ids)
            depends.append("T0.case.trec-covid.minilm_mpnet")
        elif cell_role == "scheduler":
            depends.extend(mapping_ids)
        tasks.append({**common, "task_id": task_id, "experiment": "E2", "phase": "official",
            "config_overrides": resolved, "profile_hash": None if is_trec else cfg["experiment"]["profile_hash"],
            "tuning_scope": profile["scope"], "input_refs": profile["inputs"] if not is_trec else {"dataset": "trec-covid"},
            "variant_id": variant, "overrides": overrides,
            "run_budget_policy": RUN_BUDGET_POLICY, "cell_role": cell_role,
            "dataset_case": "trec-covid" if is_trec else "fiqa",
            "depends_on": depends, "priority": 80 if not is_trec else 5})
        if is_trec:
            continue
        if cell_role == "mapping":
            mapping_ids.append(task_id)
        else:
            scheduler_ids.append(task_id)
    from .queue import validate_jobs
    return validate_jobs(tasks)
