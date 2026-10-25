"""E4 reduced-scale readiness tasks for the frozen v3 50k manifest."""

from copy import deepcopy
from pathlib import Path
import resource
import shutil
import time

import numpy as np

from .config import load_tuning_profiles, redacted_config, validate_tuning_profile
from .data.prepare import validate_prepared
from .data.splits import sample_document_pools
from .data.store import DocumentStore, RowSubsetDocumentStore
from .encoders import build_encoder, model_specs, resolve_model
from .experiments import finalize_run, source_hash
from .hf_sync import snapshot_source
from .index import ExactIndex, HnswIndex, load_index, validate_ann_snapshot
from .io import digest, file_digest, read_json, write_json
from .migration import bootstrap_migration
from .runtime import probe_hardware, require_target_hardware
from .scale_manifest import (DOCUMENT_CAP, SCALE_VARIANT, freeze_common_manifest,
                             load_common_manifest, manifest_path)
from .experiments_scale import (_encode_queries, _query_records, _run_scale_scheduler_probe,
                                _traffic_proxies)
from .vectors import (PaidEmbeddingAccessor, RowSubsetVectorStore, VectorStore,
                      encode_corpus, vector_cache_key)


RUN_BUDGET_POLICY = "compact_v1"
E4_TASKS = ("subset_probe", "full_bootstrap", "restore_footprint")
SUBSET_SIZE = DOCUMENT_CAP
SUBSET_SEED = 20261020


def _scale_paths(cfg):
    data = Path(cfg["paths"]["data"]) / "processed"
    return data / "msmarco-docs-v1", data / "orcas"


def _profile_context(cfg, root, ann_parent_verified=False, validated_releases=None):
    root = Path(root)
    profile_hash = cfg["experiment"].get("profile_hash")
    if not profile_hash:
        raise ValueError("E4_PROFILE_REQUIRED: T0.scale profile is required")
    profiles = load_tuning_profiles(root / cfg["tuning"]["lock_path"])
    profile = profiles["profiles"].get(profile_hash)
    if profile is None or profile.get("scope") != "scale":
        raise ValueError("E4_PROFILE_REQUIRED: unknown T0.scale profile")
    runtime = profile.get("selections", {}).get("runtime", {})
    batches = runtime.get("batches", {})
    if any(role not in batches or int(batches[role]) < 1 for role in ("old", "new")):
        raise ValueError("E4_PROFILE_REQUIRED: scale runtime batches are missing")
    profile_task = {"phase": "official", "profile_hash": profile_hash,
                    "tuning_scope": "scale", "input_refs": profile["inputs"],
                    "variant_id": "primary", "overrides": {},
                    "allow_ann_from_verified_parent": ann_parent_verified}
    validate_tuning_profile(profile_task, cfg, profiles)
    source_run = profile["selections"].get("source_run")
    if not source_run:
        raise ValueError("E4_PROFILE_REQUIRED: profile has no source run")
    source_dir = root / cfg["paths"]["runs"] / source_run
    if not (source_dir / "summary.json").exists():
        raise ValueError("E4_PROFILE_REQUIRED: T0.scale summary is missing")
    if read_json(source_dir / "summary.json").get("compute_status") != "COMPUTE_DONE":
        raise ValueError("E4_PROFILE_REQUIRED: T0.scale is not compute-complete")
    docs, orcas = _scale_paths(cfg)
    if validated_releases is None:
        docs_manifest = validate_prepared(docs)
        orcas_manifest = validate_prepared(orcas)
    else:
        docs_manifest = validated_releases["documents"]
        orcas_manifest = validated_releases["orcas"]
    if orcas_manifest.get("documents_release_hash") != docs_manifest["release_hash"]:
        raise ValueError("E4_INPUT_RELEASE_MISMATCH: ORCAS uses another document release")
    if cfg["experiment"].get("scale_variant") != SCALE_VARIANT:
        raise ValueError("E4_SCALE_VARIANT_REQUIRED: e4e567_scale_v3_50k")
    scale_manifest = load_common_manifest(cfg, root, source_run, validated_releases)
    if cfg["experiment"].get("scale_manifest_hash") != scale_manifest["manifest_hash"]:
        raise ValueError("E4_SCALE_MANIFEST_HASH_REQUIRED: config does not pin manifest")
    return {"profile_hash": profile_hash, "profile": profile, "source_run": source_run,
            "source_dir": source_dir, "docs": docs, "orcas": orcas,
            "docs_manifest": docs_manifest, "orcas_manifest": orcas_manifest,
            "scale_variant": SCALE_VARIANT, "scale_manifest": scale_manifest}


def _run_dir(cfg, task_name, locked):
    return Path(cfg["paths"]["runs"]) / f"E4-scale-{task_name}-{digest(locked)[:12]}"


def _peak_rss_bytes():
    # Linux reports KiB for ru_maxrss.
    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024)


def _artifact_hash(run_dir):
    """Hash the completed E4 payload without creating a summary hash cycle."""
    files = {}
    for path in sorted(Path(run_dir).rglob("*")):
        # sync.json is added by finalize_run after this identity is computed;
        # it is a receipt, not part of the immutable E4 compute payload.
        if (not path.is_file() or path.name in {"summary.json", "sync.json"}
                or "source" in path.parts):
            continue
        files[str(path.relative_to(run_dir))] = file_digest(path)
    return digest(files)


def _write_header(run_dir, root, locked, context, environment):
    run_dir.mkdir(parents=True, exist_ok=True)
    write_json(run_dir / "config.lock.json", locked)
    write_json(run_dir / "environment.json", environment)
    write_json(run_dir / "dataset_manifest.json", {
        "documents": context["docs_manifest"], "orcas": context["orcas_manifest"],
        "common_scale": {key: value for key, value in context["scale_manifest"].items()
                         if key not in {"document_rows_array", "path"}}})
    common_manifest = context["scale_manifest"]
    common_manifest_payload = {key: value for key, value in common_manifest.items()
                               if key not in {"document_rows_array", "path",
                                              "document_rows_path_resolved"}}
    write_json(run_dir / "common_scale_manifest.json", common_manifest_payload)
    shutil.copyfile(common_manifest["document_rows_path_resolved"],
                    run_dir / "common_scale_document_rows.npy")
    write_json(run_dir / "reference_inputs.json", {
        "source_run": context["source_run"], "profile_hash": context["profile_hash"],
        "scale_variant": context["scale_variant"],
        "common_scale_manifest_hash": context["scale_manifest"]["manifest_hash"],
        "official_doc_pool": DOCUMENT_CAP, "orcas_group_cap": 5000,
        "claim_scope": "reduced_scale_pilot",
        "quality_labels_opened": False,
        "scope": "E4 reduced-scale readiness; no full-corpus quality claim"})
    snapshot_source(root, run_dir)


def _subset_probe(cfg, context, run_dir, timing):
    source_dir = context["source_dir"]
    subset_manifest = read_json(source_dir / "subset_manifest.json")
    parent_rows = np.load(source_dir / "subset_rows.npy", allow_pickle=False)
    subset_rows = context["scale_manifest"]["document_rows_array"]
    subset_new_parent = np.load(source_dir / "subset_new.npy", mmap_mode="r", allow_pickle=False)
    subset_new = subset_new_parent[:SUBSET_SIZE]
    q_tune = np.load(source_dir / "q_tune.npy", mmap_mode="r", allow_pickle=False)
    doc_ids = (context["docs"] / "doc_ids.txt").read_text().splitlines()
    if (len(parent_rows) != 100_000 or subset_manifest.get("rows") != 100_000 or
            subset_manifest.get("seed") != SUBSET_SEED or
            not np.array_equal(subset_rows, parent_rows[:SUBSET_SIZE]) or
            len(subset_new_parent) != len(parent_rows)):
        raise ValueError("E4_SUBSET_GATE_FAILED: common 50k child is not the frozen T0 prefix")
    ids = [doc_ids[int(row)] for row in subset_rows]
    selected = context["profile"]["selections"].get("search", {})
    candidates = int(selected.get("candidates", 50))
    ef_search = int(selected.get("ef_search", 200))
    exact = ExactIndex(subset_new, ids, np.ones(len(ids), dtype=bool),
                       chunk_rows=cfg["search"]["chunk_rows"])
    started = time.monotonic()
    ann = HnswIndex(exact.vectors, exact.ids, exact.fidelity, exact.calibration,
                    chunk_rows=exact.chunk_rows, candidates=candidates,
                    ef_search=ef_search, M=cfg["search"]["M"],
                    ef_construction=cfg["search"]["ef_construction"],
                    threads=cfg["search"]["threads"], seed=17)
    fidelity = validate_ann_snapshot(ann, exact, np.asarray(q_tune, dtype=np.float32))
    timing.append({"component": "subset_graph_fidelity",
                   "wall_seconds": time.monotonic() - started,
                   "source": "measured", "rows": len(ids)})
    if (fidelity["candidate_recall_at_11"] < 0.99 or
            fidelity["serving_recall_at_10"] < 0.99):
        raise ValueError("E4_SUBSET_ANN_GATE_FAILED: subset graph is below 0.99 fidelity")
    probe = run_dir / "subset_restore_probe"
    started = time.monotonic()
    ann.save_index(probe)
    restored = load_index(probe)
    restore_fidelity = validate_ann_snapshot(
        restored, exact, np.asarray(q_tune, dtype=np.float32))
    timing.append({"component": "subset_graph_restore",
                   "wall_seconds": time.monotonic() - started, "source": "measured"})
    shutil.rmtree(probe, ignore_errors=True)

    # Re-run the readiness scheduler probe on the frozen child itself.  The
    # older T0.scale scheduler rows are useful provenance, but they cannot
    # certify this 50k/5k variant because they used a different corpus and
    # ORCAS group cap.
    root = context["source_dir"].parents[1]
    specs = {role: resolve_model(spec, cfg["paths"], root)
             for role, spec in model_specs("arctic", root).items()}
    full_key = vector_cache_key(context["docs_manifest"], specs["old"], "e4_full_old")
    full_path = Path(cfg["paths"]["cache"]) / "vectors" / f"e4-full-old-{full_key}"
    if not full_path.is_dir():
        raise ValueError("E4_SUBSET_GREEDY_GATE_FAILED: validated full old cache is missing")
    old_full = VectorStore(full_path, full_key)
    if len(old_full) != len(doc_ids):
        raise ValueError("E4_SUBSET_GREEDY_GATE_FAILED: full old cache row count mismatch")
    old = RowSubsetVectorStore(old_full, subset_rows)
    pools = sample_document_pools(ids, cfg)
    roles = read_json(context["orcas"] / "splits" / "query_roles.json")["roles"]
    records, schedule = _query_records(context["orcas"], roles, group_cap=5000)
    query_cfg = deepcopy(cfg)
    query_cfg["models"]["batch_size"] = int(
        context["profile"]["selections"]["runtime"]["batches"]["new"])
    queries = _encode_queries(records, roles, specs["new"], query_cfg, root, timing)
    proxies, join = _traffic_proxies(context["orcas"], schedule, subset_rows)
    probe_cfg = deepcopy(cfg)
    residual = context["profile"]["selections"]["map"]["residual_mlp"]
    if residual.get("lr") is not None:
        probe_cfg["mapping"]["lr"] = residual["lr"]
    scheduler_rows = _run_scale_scheduler_probe(
        ids, old, subset_new, pools, probe_cfg, queries, roles, schedule, proxies,
        run_dir, timing)
    greedy = next((row for row in scheduler_rows if row.get("scheduler") == "greedy"), None)
    if (not greedy or greedy.get("restore") != "PASS"
            or any(row.get("restore") != "PASS" for row in scheduler_rows)):
        raise ValueError("E4_SUBSET_GREEDY_GATE_FAILED: reduced scheduler restore failed")
    return {"task": "subset_probe", "subset_size": len(ids), "subset_seed": SUBSET_SEED,
            "fidelity": fidelity, "restore_fidelity": restore_fidelity,
            "greedy_probe": greedy, "scheduler_rows": scheduler_rows,
            "orcas_join": join, "orcas_group_cap": 5000,
            "common_scale_manifest_hash": context["scale_manifest"]["manifest_hash"],
            "quality_claim": False, "correctness_gate": "PASS"}


def _encode_full_vectors(cfg, context, root, timing):
    full_store = DocumentStore(context["docs"])
    subset_rows = context["scale_manifest"]["document_rows_array"]
    store = RowSubsetDocumentStore(full_store, subset_rows)
    specs = {role: resolve_model(spec, cfg["paths"], root)
             for role, spec in model_specs("arctic", root).items()}
    cache_root = Path(cfg["paths"]["cache"]) / "vectors"
    stores = {}
    batches = context["profile"]["selections"]["runtime"]["batches"]
    subset_manifest = {**context["docs_manifest"],
                       "release_hash": digest({
                           "release": context["docs_manifest"]["release_hash"],
                           "scale_manifest": context["scale_manifest"]["manifest_hash"]})}
    for role, spec in specs.items():
        key = vector_cache_key(subset_manifest, spec, f"e4_v3_{role}")
        output = cache_root / f"e4-v3-{role}-{key}"
        if role == "old":
            full_key = vector_cache_key(context["docs_manifest"], spec, "e4_full_old")
            full_path = cache_root / f"e4-full-old-{full_key}"
            if full_path.is_dir() and (full_path / "manifest.json").exists():
                base = VectorStore(full_path, full_key)
                if len(base) != len(full_store):
                    raise ValueError("E4_OLD_CACHE_ROWS_MISMATCH: full old cache")
                stores[role] = RowSubsetVectorStore(base, subset_rows)
                timing.append({"component": "encode_full_old", "wall_seconds": 0.0,
                               "source": "validated_full_cache_view", "rows": len(stores[role]),
                               "batch_size": int(batches[role]), "cache_key": full_key})
                continue
        started = time.monotonic()
        encoder = build_encoder(spec, cfg["execution"]["device"], int(batches[role]))
        try:
            # Keep the frozen scale profile's forward batch as the primary
            # contract.  Host-side reader batching is optimized in
            # encode_corpus, while dynamic token-budget packing remains an
            # explicit, separately profiled variant and is not used here.
            stores[role] = encode_corpus(store, encoder, output, key)
            timing.append({"component": f"encode_full_{role}",
                           "wall_seconds": time.monotonic() - started,
                           "source": "measured", "rows": len(stores[role]),
                           "batch_size": int(batches[role]),
                           "encoder_cost": dict(encoder.cost), "cache_key": key,
                           "scale_variant": context["scale_variant"]})
        finally:
            encoder.close()
    return store, stores["old"], stores["new"], specs


def _full_bootstrap(cfg, root, context, run_dir, timing):
    _store, old, new, _specs = _encode_full_vectors(cfg, context, root, timing)
    full_doc_ids = (context["docs"] / "doc_ids.txt").read_text().splitlines()
    doc_ids = [full_doc_ids[int(row)]
               for row in context["scale_manifest"]["document_rows_array"]]
    if len(old) != len(doc_ids) or len(new) != len(doc_ids):
        raise ValueError("E4_FULL_VECTOR_GATE_FAILED: cache rows differ from manifest")
    pools = sample_document_pools(doc_ids, cfg)
    reserved = set(pools["train"]) | set(pools["validation"])
    accessor = PaidEmbeddingAccessor(
        lambda rows: new.get_rows(rows),
        {"train": pools["train"], "validation": pools["validation"],
         "backfill": set(range(len(doc_ids))) - reserved},
        len(doc_ids), mode="cached_access")
    candidate = deepcopy(cfg)
    candidate["mapping"]["kind"] = "residual_mlp"
    candidate["mapping"]["lr"] = context["profile"]["selections"]["map"]["residual_mlp"]["lr"]
    candidate["search"]["backend"] = "hnsw"
    selected = context["profile"]["selections"].get("search", {})
    candidate["search"]["candidates"] = int(selected.get("candidates", 50))
    candidate["search"]["ef_search"] = int(selected.get("ef_search", 200))
    candidate["calibration"]["enabled"] = False
    started = time.monotonic()
    state = bootstrap_migration(
        doc_ids, pools, old, accessor, candidate, map_seed=17, traffic_seed=101,
        calibration_queries={"cal_fit": {}, "cal_check": {}})
    timing.append({"component": "full_bootstrap",
                   "wall_seconds": time.monotonic() - started,
                   "source": "measured", "documents": len(doc_ids),
                   "mode": "cached_access"})
    exact = ExactIndex(state.index.vectors, state.index.ids, state.index.fidelity,
                       state.index.calibration, state.index.chunk_rows)
    q_tune = np.load(context["source_dir"] / "q_tune.npy",
                     mmap_mode="r", allow_pickle=False)
    q_tune = np.asarray(q_tune, dtype=np.float32)
    fidelity = validate_ann_snapshot(state.index, exact, q_tune)
    if (fidelity["candidate_recall_at_11"] < 0.99 or
            fidelity["serving_recall_at_10"] < 0.99):
        raise ValueError("E4_FULL_ANN_GATE_FAILED: full stored graph is below 0.99 fidelity")
    graph_dir = run_dir / "full_index"
    started = time.monotonic()
    state.index.save_index(graph_dir)
    restored = load_index(graph_dir)
    roundtrip = validate_ann_snapshot(restored, exact, q_tune)
    timing.append({"component": "full_graph_save_restore",
                   "wall_seconds": time.monotonic() - started, "source": "measured"})
    if roundtrip["serving_recall_at_10"] < 0.99:
        raise ValueError("E4_FULL_RESTORE_GATE_FAILED: restored graph is below 0.99 fidelity")
    footprint_bytes = sum(p.stat().st_size for p in graph_dir.rglob("*") if p.is_file())
    return {"task": "full_bootstrap", "documents": len(doc_ids),
            "old_cache_rows": len(old), "new_cache_rows": len(new),
            "runtime_batches": {role: int(context["profile"]["selections"]["runtime"]["batches"][role])
                                for role in ("old", "new")},
            "fidelity": fidelity, "restored_fidelity": roundtrip,
            "graph_footprint_bytes": footprint_bytes,
            "peak_rss_bytes": _peak_rss_bytes(), "quality_claim": False,
            "correctness_gate": "PASS",
            "search": {"candidates": candidate["search"]["candidates"],
                       "ef_search": candidate["search"]["ef_search"]}}


def _restore_footprint(cfg, context, run_dir, timing):
    full_run = context["full_run_dir"]
    graph_dir = full_run / "full_index"
    if not (graph_dir / "index.json").exists():
        raise ValueError("E4_RESTORE_REQUIRED: full bootstrap graph is missing")
    q_tune = np.asarray(np.load(context["source_dir"] / "q_tune.npy",
                                mmap_mode="r", allow_pickle=False), dtype=np.float32)
    started = time.monotonic()
    restored = load_index(graph_dir)
    loaded_seconds = time.monotonic() - started
    probe = run_dir / "restore_probe"
    started = time.monotonic()
    restored.save_index(probe)
    roundtrip = load_index(probe)
    save_restore_seconds = time.monotonic() - started
    exact = ExactIndex(restored.vectors, restored.ids, restored.fidelity,
                       restored.calibration, restored.chunk_rows)
    fidelity = validate_ann_snapshot(roundtrip, exact, q_tune)
    shutil.rmtree(probe, ignore_errors=True)
    timing.extend([
        {"component": "full_graph_load", "wall_seconds": loaded_seconds,
         "source": "measured"},
        {"component": "full_graph_roundtrip", "wall_seconds": save_restore_seconds,
         "source": "measured"},
    ])
    if fidelity["serving_recall_at_10"] < 0.99:
        raise ValueError("E4_RESTORE_FIDELITY_FAILED: restored graph is below 0.99")
    bytes_on_disk = sum(p.stat().st_size for p in graph_dir.rglob("*") if p.is_file())
    return {"task": "restore_footprint", "graph_footprint_bytes": bytes_on_disk,
            "load_seconds": loaded_seconds, "roundtrip_seconds": save_restore_seconds,
            "peak_rss_bytes": _peak_rss_bytes(), "fidelity": fidelity,
            "quality_claim": False, "correctness_gate": "PASS"}


def run_scale_task(cfg, root):
    """Run one immutable E4 readiness task and sync only a passing result."""
    root = Path(root)
    if cfg["execution"]["phase"] != "official":
        raise ValueError("E4 tasks must be official")
    require_target_hardware(cfg, probe_hardware())
    task_name = cfg["experiment"].get("scale_task")
    if task_name not in E4_TASKS:
        raise ValueError("E4_SCALE_TASK_REQUIRED: unknown task")
    context = _profile_context(cfg, root)
    if task_name == "restore_footprint":
        state_path = Path(cfg["paths"]["state"]) / "tasks.json"
        state = read_json(state_path)
        dependency = cfg["experiment"].get("full_bootstrap_task_id")
        record = state.get("tasks", {}).get(dependency, {})
        if (record.get("status") != "COMPUTE_DONE" or
                record.get("sync_status") != "VERIFIED" or
                record.get("handle_alive") is not False):
            raise ValueError("E4_RESTORE_REQUIRED: full bootstrap dependency is not verified")
        context["full_run_dir"] = Path(record["run_dir"])
    locked = {"config": redacted_config(cfg), "source_hash": source_hash(root),
              "run_budget_policy": RUN_BUDGET_POLICY, "scale_task": task_name,
              "profile_hash": context["profile_hash"], "source_run": context["source_run"],
              "scale_variant": context["scale_variant"],
              "common_scale_manifest_hash": context["scale_manifest"]["manifest_hash"],
              "official_doc_pool": DOCUMENT_CAP, "orcas_group_cap": 5000,
              "claim_scope": "reduced_scale_pilot",
              "documents_release": context["docs_manifest"]["release_hash"],
              "orcas_release": context["orcas_manifest"]["release_hash"]}
    run_dir = _run_dir(cfg, task_name, locked)
    if (run_dir / "summary.json").exists():
        summary = read_json(run_dir / "summary.json")
        if summary.get("compute_status") == "COMPUTE_DONE":
            return finalize_run(run_dir, summary, cfg, root)
        raise ValueError("Failed E4 task is preserved; use a new source/config revision")
    environment = probe_hardware()
    _write_header(run_dir, root, locked, context, environment)
    timing, summary = [], {
        "compute_status": "FAILED", "phase": "official", "outcome": "inconclusive",
        "performance_claim": False, "expect_classification": "KHỚP",
        "run_budget_policy": RUN_BUDGET_POLICY, "scale_task": task_name,
        "profile_hash": context["profile_hash"], "scale_variant": context["scale_variant"],
        "common_scale_manifest_hash": context["scale_manifest"]["manifest_hash"],
        "official_doc_pool": DOCUMENT_CAP, "orcas_group_cap": 5000,
        "claim_scope": "reduced_scale_pilot", "e4_artifact_id": run_dir.name,
        "e4_artifact_hash": None, "parent_e4_artifact_id": None,
        "parent_e4_artifact_hash": None,
    }
    try:
        if task_name == "subset_probe":
            metrics = _subset_probe(cfg, context, run_dir, timing)
        elif task_name == "full_bootstrap":
            metrics = _full_bootstrap(cfg, root, context, run_dir, timing)
        else:
            metrics = _restore_footprint(cfg, context, run_dir, timing)
        write_json(run_dir / "scale_metrics.json", metrics)
        write_json(run_dir / "timing.json",
                   {"records": timing, "performance_claim": False,
                    "exclusive": "unverified"})
        write_json(run_dir / "estimate.json", {
            "scope": "E4", "task": task_name, "run_budget_policy": RUN_BUDGET_POLICY,
            "scale_variant": SCALE_VARIANT, "official_doc_pool": DOCUMENT_CAP,
            "orcas_group_cap": 5000, "claim_scope": "reduced_scale_pilot",
            "measured": {r["component"]: r["wall_seconds"] for r in timing},
            "full_quality": "unmeasured_until_E5", "concurrency": 1})
        summary["e4_artifact_hash"] = _artifact_hash(run_dir)
        summary.update(compute_status="COMPUTE_DONE", metrics=metrics,
                       correctness_gate="PASS", target_hardware_pass=True)
    except Exception as exc:
        summary.update(error_type=type(exc).__name__, reason=str(exc))
        write_json(run_dir / "scale_metrics.json",
                   {"status": "FAILED", "reason": summary["reason"]})
        write_json(run_dir / "timing.json",
                   {"records": timing, "performance_claim": False})
    return finalize_run(run_dir, summary, cfg, root)


def build_scale_tasks(cfg, root):
    """Declare the three compact_v1 E4 tasks behind a verified T0.scale."""
    root = Path(root)
    from .queue import validate_jobs
    state_path = Path(cfg["paths"]["state"]) / "tasks.json"
    if not state_path.exists():
        raise ValueError("E4_DEPENDENCY_REQUIRED: state/tasks.json")
    state = read_json(state_path)
    # The dependency is the verified T0.scale profile, not a particular task
    # naming convention.  The speed-optimized T0 revision has the same locked
    # scale scope and provenance but intentionally does not end in `.freeze`.
    # Keep the result/provenance gates strict so failed, cancelled, or unrelated
    # diagnostic tasks can never open E4.
    verified = []
    for identifier, record in state.get("tasks", {}).items():
        result = record.get("result") or {}
        if not identifier.startswith("T0.scale."):
            continue
        if (record.get("status") != "COMPUTE_DONE"
                or record.get("sync_status") != "VERIFIED"
                or record.get("handle_alive") is not False):
            continue
        if (result.get("compute_status") != "COMPUTE_DONE"
                or result.get("sync_status") != "VERIFIED"
                or result.get("scope") != "T0.scale"
                or not result.get("profile_hash")
                or not record.get("run_dir")):
            continue
        verified.append((identifier, record))
    if len(verified) != 1:
        raise ValueError("E4_DEPENDENCY_REQUIRED: one verified T0.scale profile is required")
    t0_id, t0_record = verified[0]
    t0_run = Path(t0_record["run_dir"]).relative_to(
        root / cfg["paths"]["runs"]).as_posix()
    t0_summary = read_json(root / cfg["paths"]["runs"] / t0_run / "summary.json")
    profile_hash = t0_summary.get("profile_hash")
    if not profile_hash:
        raise ValueError("E4_DEPENDENCY_REQUIRED: T0.scale profile hash is missing")
    profiles = load_tuning_profiles(root / cfg["tuning"]["lock_path"])
    profile = profiles["profiles"].get(profile_hash)
    if profile is None or profile.get("scope") != "scale":
        raise ValueError("E4_DEPENDENCY_REQUIRED: T0.scale profile is not locked")
    common_manifest = freeze_common_manifest(cfg, root, t0_run)
    manifest_relative = manifest_path(cfg, root).relative_to(root).as_posix()
    revision = digest({"source": source_hash(root), "profile_hash": profile_hash,
                       "budget": RUN_BUDGET_POLICY, "scale_variant": SCALE_VARIANT,
                       "manifest_hash": common_manifest["manifest_hash"]})[:12]
    common = {
        "config": "configs/experiments/e4.yaml", "phase": "official",
        "measurement_mode": "exclusive", "development_hardware": False,
        "tuning_scope": "scale", "input_refs": profile["inputs"],
        "profile_hash": profile_hash, "variant_id": "primary", "overrides": {},
        "run_budget_policy": RUN_BUDGET_POLICY,
        "resources": {"gpu_device": 0, "gpu_memory_gib": 12, "host_ram_gib": 48,
                      "cpu_cores": 8, "disk_scratch_gib": 96, "io_heavy": True},
    }
    ids = {name: f"E4.scale.{name}.{digest({'name': name, 'revision': revision})[:12]}"
           for name in E4_TASKS}
    tasks = []
    previous = t0_id
    for name in E4_TASKS:
        overrides = {
            "experiment": {"profile_hash": profile_hash, "tuning_scope": "scale",
                           "scale_task": name, "source_run": t0_run,
                           "scale_variant": SCALE_VARIANT,
                           "scale_manifest_hash": common_manifest["manifest_hash"],
                           "scale_manifest_path": manifest_relative},
        }
        if name == "restore_footprint":
            overrides["experiment"]["full_bootstrap_task_id"] = ids["full_bootstrap"]
        tasks.append({**common, "task_id": ids[name], "experiment": "E4",
                      "config_overrides": overrides, "depends_on": [previous],
                      "priority": 70})
        previous = ids[name]
    return validate_jobs(tasks)
