"""E4 scale-feasibility and full-bootstrap readiness tasks.

E4 is an operability/readiness gate.  It uses the frozen T0.scale settings,
keeps the 100k subset explicitly labelled, and never opens judged quality
labels.  Full-corpus vectors are cached in validated shards so the bootstrap
does not require a second in-memory copy of the old encoder output.
"""

from copy import deepcopy
from pathlib import Path
import resource
import shutil
import time

import numpy as np

from .config import load_tuning_profiles, redacted_config, validate_tuning_profile
from .data.prepare import validate_prepared
from .data.splits import sample_document_pools
from .data.store import DocumentStore
from .encoders import build_encoder, model_specs, resolve_model
from .experiments import finalize_run, source_hash
from .hf_sync import snapshot_source
from .index import ExactIndex, HnswIndex, load_index, validate_ann_snapshot
from .io import digest, read_json, write_json
from .migration import bootstrap_migration
from .progress import update_checklist
from .runtime import probe_hardware, require_target_hardware
from .vectors import PaidEmbeddingAccessor, encode_corpus, vector_cache_key


RUN_BUDGET_POLICY = "compact_v1"
E4_TASKS = ("subset_probe", "full_bootstrap", "restore_footprint")
SUBSET_SIZE = 100_000
SUBSET_SEED = 20261020


def _scale_paths(cfg):
    data = Path(cfg["paths"]["data"]) / "processed"
    return data / "msmarco-docs-v1", data / "orcas"


def _profile_context(cfg, root):
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
                    "variant_id": "primary", "overrides": {}}
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
    docs_manifest = validate_prepared(docs)
    orcas_manifest = validate_prepared(orcas)
    if orcas_manifest.get("documents_release_hash") != docs_manifest["release_hash"]:
        raise ValueError("E4_INPUT_RELEASE_MISMATCH: ORCAS uses another document release")
    return {"profile_hash": profile_hash, "profile": profile, "source_run": source_run,
            "source_dir": source_dir, "docs": docs, "orcas": orcas,
            "docs_manifest": docs_manifest, "orcas_manifest": orcas_manifest}


def _run_dir(cfg, task_name, locked):
    return Path(cfg["paths"]["runs"]) / f"E4-scale-{task_name}-{digest(locked)[:12]}"


def _peak_rss_bytes():
    # Linux reports KiB for ru_maxrss.
    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024)


def _write_header(run_dir, root, locked, context, environment):
    run_dir.mkdir(parents=True, exist_ok=True)
    write_json(run_dir / "config.lock.json", locked)
    write_json(run_dir / "environment.json", environment)
    write_json(run_dir / "dataset_manifest.json", {
        "documents": context["docs_manifest"], "orcas": context["orcas_manifest"]})
    write_json(run_dir / "reference_inputs.json", {
        "source_run": context["source_run"], "profile_hash": context["profile_hash"],
        "quality_labels_opened": False,
        "scope": "E4 scale feasibility/readiness; no full-scale quality claim"})
    snapshot_source(root, run_dir)


def _subset_probe(cfg, context, run_dir, timing):
    source_dir = context["source_dir"]
    subset_manifest = read_json(source_dir / "subset_manifest.json")
    subset_rows = np.load(source_dir / "subset_rows.npy", allow_pickle=False)
    subset_new = np.load(source_dir / "subset_new.npy", mmap_mode="r", allow_pickle=False)
    q_tune = np.load(source_dir / "q_tune.npy", mmap_mode="r", allow_pickle=False)
    doc_ids = (context["docs"] / "doc_ids.txt").read_text().splitlines()
    if (len(subset_rows) != SUBSET_SIZE or subset_manifest.get("rows") != SUBSET_SIZE or
            subset_manifest.get("seed") != SUBSET_SEED):
        raise ValueError("E4_SUBSET_GATE_FAILED: fixed uniform subset is missing or mis-sized")
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
    scale_metrics = read_json(source_dir / "scale_metrics.json")
    greedy = next((row for row in scale_metrics.get("scheduler_rows", [])
                   if row.get("scheduler") == "greedy"), None)
    if not greedy or greedy.get("restore") != "PASS":
        raise ValueError("E4_SUBSET_GREEDY_GATE_FAILED: T0 greedy probe is unavailable")
    return {"task": "subset_probe", "subset_size": len(ids), "subset_seed": SUBSET_SEED,
            "fidelity": fidelity, "restore_fidelity": restore_fidelity,
            "greedy_probe": greedy, "orcas_join": scale_metrics.get("orcas_join"),
            "quality_claim": False, "correctness_gate": "PASS"}


def _encode_full_vectors(cfg, context, root, timing):
    store = DocumentStore(context["docs"])
    specs = {role: resolve_model(spec, cfg["paths"], root)
             for role, spec in model_specs("arctic", root).items()}
    cache_root = Path(cfg["paths"]["cache"]) / "vectors"
    stores = {}
    batches = context["profile"]["selections"]["runtime"]["batches"]
    for role, spec in specs.items():
        key = vector_cache_key(context["docs_manifest"], spec, f"e4_full_{role}")
        output = cache_root / f"e4-full-{role}-{key}"
        started = time.monotonic()
        encoder = build_encoder(spec, cfg["execution"]["device"], int(batches[role]))
        try:
            stores[role] = encode_corpus(store, encoder, output, key)
            timing.append({"component": f"encode_full_{role}",
                           "wall_seconds": time.monotonic() - started,
                           "source": "measured", "rows": len(stores[role]),
                           "batch_size": int(batches[role]),
                           "encoder_cost": dict(encoder.cost), "cache_key": key})
        finally:
            encoder.close()
    return store, stores["old"], stores["new"], specs


def _full_bootstrap(cfg, root, context, run_dir, timing):
    _store, old, new, _specs = _encode_full_vectors(cfg, context, root, timing)
    doc_ids = (context["docs"] / "doc_ids.txt").read_text().splitlines()
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
        "profile_hash": context["profile_hash"],
    }
    update_checklist(root, run_dir.name,
                     {**summary, "compute_status": "RUNNING", "sync_status": "PENDING"})
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
            "measured": {r["component"]: r["wall_seconds"] for r in timing},
            "full_quality": "unmeasured_until_E5", "concurrency": 1})
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
    verified = [(identifier, record) for identifier, record in state.get("tasks", {}).items()
                if identifier.startswith("T0.scale.") and identifier.endswith(".freeze")
                and record.get("status") == "COMPUTE_DONE"
                and record.get("sync_status") == "VERIFIED"
                and record.get("handle_alive") is False]
    if len(verified) != 1:
        raise ValueError("E4_DEPENDENCY_REQUIRED: one verified T0.scale freeze is required")
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
    revision = digest({"source": source_hash(root), "profile_hash": profile_hash,
                       "budget": RUN_BUDGET_POLICY})[:12]
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
                           "scale_task": name, "source_run": t0_run},
        }
        if name == "restore_footprint":
            overrides["experiment"]["full_bootstrap_task_id"] = ids["full_bootstrap"]
        tasks.append({**common, "task_id": ids[name], "experiment": "E4",
                      "config_overrides": overrides, "depends_on": [previous],
                      "priority": 70})
        previous = ids[name]
    return validate_jobs(tasks)
