"""E3 systems pilot: exact/HNSW fidelity, update cadence and serving recovery.

The systems tasks consume one immutable FiQA stored-vector snapshot produced by
the verified E2 chain.  They do not refit a map or select a new ANN profile;
the profile selected by T0.core is part of every task's locked inputs.
"""

from copy import deepcopy
import shutil
import threading
import time
from pathlib import Path

import numpy as np

from .config import load_tuning_profiles, redacted_config, validate_tuning_profile
from .experiments import finalize_run, source_hash
from .hf_sync import snapshot_source
from .index import HnswIndex, load_index, validate_ann_snapshot
from .io import digest, file_digest, read_json, write_json
from .runtime import cost_scope, probe_hardware, require_target_hardware


RUN_BUDGET_POLICY = "compact_v1"
E3_TASKS = (
    "exact_reference",
    "hnsw_fixed_snapshot",
    "cadence_1pct",
    "cadence_5pct",
    "cadence_10pct",
    "serving_save_load",
)


def _absolute(root, value):
    path = Path(value)
    return path if path.is_absolute() else Path(root) / path


def _complete_checkpoint(run_dir):
    checkpoints = Path(run_dir) / "checkpoints"
    complete = []
    for path in checkpoints.glob("accessed-*"):
        marker = path / "checkpoint.json"
        if marker.exists() and read_json(marker).get("complete"):
            complete.append((int(path.name.rsplit("-", 1)[1]), path))
    if not complete:
        raise ValueError("E3_SNAPSHOT_REQUIRED: no complete E2 snapshot checkpoint")
    return max(complete, key=lambda item: item[0])[1]


def _snapshot_context(cfg, root):
    root = Path(root)
    profile_hash = cfg["experiment"].get("profile_hash")
    if not profile_hash:
        raise ValueError("E3_PROFILE_REQUIRED: frozen core profile is required")
    profiles = load_tuning_profiles(root / cfg["tuning"]["lock_path"])
    if profile_hash not in profiles["profiles"]:
        raise ValueError("E3_PROFILE_REQUIRED: unknown frozen core profile")
    profile = profiles["profiles"][profile_hash]
    if profile.get("scope") != "core":
        raise ValueError("E3_SCOPE_REQUIRED: E3 pilot requires the FiQA core profile")
    if profile["selections"].get("ann_status") != "PASS":
        raise ValueError("ANN_GATE_FAILED: E3 cannot open without a passing T0 ANN profile")
    task = {
        "phase": "official", "profile_hash": profile_hash,
        "tuning_scope": "core", "input_refs": profile["inputs"],
        "variant_id": "primary", "overrides": {},
    }
    validate_tuning_profile(task, cfg, profiles)
    snapshot_run = cfg["experiment"].get("snapshot_run")
    if not snapshot_run:
        raise ValueError("E3_SNAPSHOT_REQUIRED: snapshot_run is not configured")
    snapshot_dir = root / cfg["paths"]["runs"] / snapshot_run
    summary_path = snapshot_dir / "summary.json"
    if not summary_path.exists() or read_json(summary_path).get("compute_status") != "COMPUTE_DONE":
        raise ValueError("E3_SNAPSHOT_REQUIRED: source run is not compute-complete")
    checkpoint = _complete_checkpoint(snapshot_dir)
    index_dir = checkpoint / "index"
    for name in ("index.json", "vectors.npy", "ids.npy", "fidelity.npy"):
        if not (index_dir / name).exists():
            raise ValueError(f"E3_SNAPSHOT_REQUIRED: missing {name}")
    q_value = cfg["experiment"].get("q_tune_cache")
    if not q_value:
        raise ValueError("E3_Q_TUNE_REQUIRED: frozen Q_tune cache is required")
    q_path = _absolute(root, q_value)
    if q_path.is_dir():
        q_path = q_path / "queries.npy"
    if not q_path.exists():
        raise ValueError("E3_Q_TUNE_REQUIRED: Q_tune cache is missing")
    q_tune = np.load(q_path, mmap_mode="r", allow_pickle=False)
    index = load_index(index_dir)
    if len(q_tune) == 0 or q_tune.ndim != 2 or q_tune.shape[1] != index.vectors.shape[1]:
        raise ValueError("E3_Q_TUNE_REQUIRED: Q_tune dimension or population is invalid")
    return {
        "profile": profile, "profile_hash": profile_hash,
        "snapshot_run": snapshot_run, "snapshot_dir": snapshot_dir,
        "checkpoint": checkpoint, "index_dir": index_dir, "index": index,
        "q_tune": np.asarray(q_tune, dtype=np.float32), "q_tune_path": q_path,
    }


def _record_fidelity(index, exact, q_tune):
    values = validate_ann_snapshot(index, exact, q_tune)
    values["gate"] = (values["candidate_recall_at_11"] >= 0.99 and
                       values["serving_recall_at_10"] >= 0.99)
    return values


def _make_hnsw(exact, cfg):
    selected = load_tuning_profiles(Path(cfg["tuning"]["lock_path"]))["profiles"][
        cfg["experiment"]["profile_hash"]]["selections"]["search"]
    return HnswIndex(exact.vectors, exact.ids, exact.fidelity, exact.calibration,
                     chunk_rows=exact.chunk_rows,
                     candidates=int(selected["candidates"]),
                     ef_search=int(selected["ef_search"]),
                     M=int(cfg["search"]["M"]),
                     ef_construction=int(cfg["search"]["ef_construction"]),
                     threads=int(cfg["search"]["threads"]), seed=17)


def _save_restore(index, path):
    index.save_index(path)
    restored = load_index(path)
    if not np.array_equal(restored.ids, index.ids) or not np.allclose(
            restored.vectors, index.vectors, atol=1e-6, rtol=0):
        raise ValueError("E3_SAVE_LOAD_FAILED: restored vectors or IDs differ")
    return restored


def _exact_task(ctx, run_dir, timing):
    exact = ctx["index"]
    q = ctx["q_tune"]
    with cost_scope("exact_reference_search", timing) as rec:
        result = exact.search(q)
        rec.update(queries=len(q), rows=len(result.rows))
    probe = run_dir / "probe_exact"
    with cost_scope("exact_save_load", timing):
        restored = _save_restore(exact, probe)
        roundtrip = restored.search(q)
    if not np.array_equal(result.rows, roundtrip.rows):
        raise ValueError("E3_EXACT_REFERENCE_FAILED: save/load changed exact ranking")
    shutil.rmtree(probe, ignore_errors=True)
    return {"task": "exact_reference", "exact_rows": int(len(result.rows)),
            "snapshot_epoch": int(exact.epoch), "correctness_gate": "PASS"}


def _hnsw_task(ctx, cfg, run_dir, timing):
    exact, q = ctx["index"], ctx["q_tune"]
    ann = _make_hnsw(exact, cfg)
    with cost_scope("hnsw_fidelity", timing):
        fidelity = _record_fidelity(ann, exact, q)
    if not fidelity["gate"]:
        raise ValueError("ANN_GATE_FAILED: fixed HNSW snapshot is below 0.99 fidelity")
    probe = run_dir / "probe_hnsw"
    with cost_scope("hnsw_save_load", timing):
        restored = _save_restore(ann, probe)
        before, after = ann.search(q), restored.search(q)
    if not np.array_equal(before.rows, after.rows):
        raise ValueError("E3_SAVE_LOAD_FAILED: HNSW ranking changed after restore")
    shutil.rmtree(probe, ignore_errors=True)
    return {"task": "hnsw_fixed_snapshot", "fidelity": fidelity,
            "selected_search": dict(ann.parameters), "correctness_gate": "PASS"}


def _cadence_task(ctx, cfg, run_dir, timing, cadence):
    exact_base, q = ctx["index"], ctx["q_tune"]
    ann = _make_hnsw(exact_base, cfg)
    exact = load_index(ctx["index_dir"])
    n = len(exact.ids)
    horizon = float(cfg["experiment"].get("systems_horizon_fraction", 1.0))
    if not 0 < horizon <= 1:
        raise ValueError("Invalid E3 systems horizon fraction")
    horizon_rows = max(1, int(np.floor(n * horizon)))
    order = np.arange(horizon_rows, dtype=np.int64)
    batch = max(1, int(np.ceil(n * cadence)))
    rng = np.random.default_rng(20261020 + int(round(cadence * 1000)))
    checks = []
    update_events = 0
    started = time.monotonic()
    stride = max(1, int(cfg["experiment"].get("systems_validation_stride", 10)))
    for start in range(0, len(order), batch):
        rows = order[start:start + batch]
        noise = rng.normal(0, 1e-5, size=(len(rows), exact.vectors.shape[1])).astype(np.float32)
        proposed = exact.vectors[rows] + noise
        proposed /= np.maximum(np.linalg.norm(proposed, axis=1, keepdims=True), 1e-12)
        ann.commit_index_update(rows, proposed, np.ones(len(rows), dtype=bool), epoch=update_events + 1)
        exact.commit_index_update(rows, proposed, np.ones(len(rows), dtype=bool), epoch=update_events + 1)
        update_events += 1
        if update_events == 1 or update_events % stride == 0 or start + len(rows) == len(order):
            with cost_scope("cadence_fidelity_check", timing) as rec:
                fidelity = _record_fidelity(ann, exact, q)
                rec.update(cadence=cadence, update_event=update_events, updated_rows=int(start + len(rows)))
            checks.append({"event": update_events, "updated_rows": int(start + len(rows)), **fidelity})
            if not fidelity["gate"]:
                raise ValueError(f"ANN_GATE_FAILED: cadence {cadence:g} lost 0.99 fidelity")
    return {"task": f"cadence_{int(cadence * 100)}pct", "cadence": cadence,
            "horizon_fraction": horizon, "updated_rows": horizon_rows,
            "update_events": update_events, "checks": checks,
            "elapsed_seconds": time.monotonic() - started,
            "correctness_gate": "PASS"}


def _synchronized_and_failure_task(ctx, cfg, run_dir, timing, failure_only=False):
    exact, q = ctx["index"], ctx["q_tune"]
    ann = _make_hnsw(exact, cfg)
    errors = []
    stop = threading.Event()
    started = threading.Event()

    def reader():
        started.set()
        try:
            while not stop.is_set():
                result = ann.search(q[: min(4, len(q))])
                if result.epoch < 0:
                    errors.append("negative_epoch")
        except Exception as exc:  # pragma: no cover - exercised by live worker
            errors.append(type(exc).__name__)

    threads = [] if failure_only else [threading.Thread(target=reader, daemon=True) for _ in range(4)]
    for thread in threads:
        thread.start()
    if threads and not started.wait(timeout=5):
        raise ValueError("E3_SERVING_FAILED: readers did not start")
    with cost_scope("synchronized_serving_updates", timing):
        for epoch in range(1, 4):
            rows = np.arange((epoch - 1) * 4, epoch * 4, dtype=np.int64)
            values = ann.vectors[rows].copy()
            values[:, 0] *= -1
            values /= np.maximum(np.linalg.norm(values, axis=1, keepdims=True), 1e-12)
            ann.commit_index_update(rows, values, np.ones(len(rows), dtype=bool), epoch=epoch)
    stop.set()
    for thread in threads:
        thread.join(timeout=5)
    if errors:
        raise ValueError(f"E3_SERVING_FAILED: {errors[0]}")
    synchronized = {"reader_threads": len(threads), "epochs_committed": 3,
                    "lock_gate": "PASS"}
    if failure_only:
        return {"task": "synchronized_serving", **synchronized}

    clean = run_dir / "probe_clean_hnsw"
    _save_restore(ann, clean)
    original = ann._write_vectors

    def failing_write(rows, values):
        original(rows, values)
        raise RuntimeError("injected failed update")

    ann._write_vectors = failing_write
    failed_update_detected = False
    try:
        ann.commit_index_update(np.array([0], dtype=np.int64), ann.vectors[:1].copy(),
                                np.ones(1, dtype=bool), epoch=99)
    except RuntimeError:
        failed_update_detected = not ann.healthy
    if not failed_update_detected:
        raise ValueError("E3_FAILED_UPDATE_PROBE: injected failure was not quarantined")
    restored = load_index(clean)
    roundtrip = restored.search(q[: min(8, len(q))])
    shutil.rmtree(clean, ignore_errors=True)
    if len(roundtrip.rows) != min(8, len(q)):
        raise ValueError("E3_FAILED_UPDATE_PROBE: clean checkpoint did not restore")
    synchronized["failed_update_detected"] = True
    synchronized["failed_update_recovered"] = True
    synchronized["correctness_gate"] = "PASS"
    return {"task": "synchronized_serving", **synchronized}


def run_systems_task(cfg, root):
    """Run one immutable E3 systems task and sync only a passing result."""
    root = Path(root)
    if cfg["execution"]["phase"] != "official":
        raise ValueError("E3 systems tasks must be official")
    require_target_hardware(cfg, probe_hardware())
    task_name = cfg["experiment"].get("system_task")
    if task_name not in E3_TASKS:
        raise ValueError("E3_SYSTEM_TASK_REQUIRED: unknown systems task")
    ctx = _snapshot_context(cfg, root)
    snapshot_marker = ctx["checkpoint"] / "checkpoint.json"
    locked = {"config": redacted_config(cfg), "source_hash": source_hash(root),
              "profile_hash": ctx["profile_hash"], "run_budget_policy": RUN_BUDGET_POLICY,
              "system_task": task_name, "snapshot_run": ctx["snapshot_run"],
              "snapshot_checkpoint": str(ctx["checkpoint"].relative_to(ctx["snapshot_dir"])),
              "snapshot_hash": file_digest(snapshot_marker),
              "q_tune_path": str(ctx["q_tune_path"].relative_to(root)),
              "q_tune_hash": file_digest(ctx["q_tune_path"]),
              "q_tune_rows": int(len(ctx["q_tune"]))}
    run_id = f"E3-fiqa-systems-{task_name}-{digest(locked)[:12]}"
    run_dir = Path(cfg["paths"]["runs"]) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    if (run_dir / "summary.json").exists():
        summary = read_json(run_dir / "summary.json")
        if summary.get("compute_status") == "COMPUTE_DONE":
            return finalize_run(run_dir, summary, cfg, root)
        raise ValueError("Failed E3 systems task is preserved; use a new source/config revision")
    write_json(run_dir / "config.lock.json", locked)
    write_json(run_dir / "environment.json", probe_hardware())
    write_json(run_dir / "tuning_profile.json", {"profile_hash": ctx["profile_hash"], **ctx["profile"]})
    write_json(run_dir / "reference_inputs.json", {
        "snapshot_run": ctx["snapshot_run"], "snapshot_checkpoint": locked["snapshot_checkpoint"],
        "q_tune_rows": len(ctx["q_tune"]), "q_tune_hash": locked["q_tune_hash"],
        "exact_reference": "stored-vector snapshot; no test labels opened",
        "cost_scope": "systems pilot; no migration quality claim",
    })
    snapshot_source(root, run_dir)
    timing, metrics = [], {}
    summary = {"compute_status": "FAILED", "phase": "official", "outcome": "inconclusive",
               "performance_claim": False, "expect_classification": "KHỚP",
               "run_budget_policy": RUN_BUDGET_POLICY, "system_task": task_name,
               "profile_hash": ctx["profile_hash"], "execution_mode": "cached_access"}
    from .progress import update_checklist
    # A running row is deliberately not a failed result.  The policy guard
    # removes it until compute and remote verification are both terminal.
    update_checklist(root, run_id, {**summary, "compute_status": "RUNNING", "sync_status": "PENDING"})
    print(f"OFFICIAL E3 STARTED: {run_id}", flush=True)
    try:
        if task_name == "exact_reference":
            metrics = _exact_task(ctx, run_dir, timing)
        elif task_name == "hnsw_fixed_snapshot":
            metrics = _hnsw_task(ctx, cfg, run_dir, timing)
        elif task_name.startswith("cadence_"):
            cadence = {"cadence_1pct": .01, "cadence_5pct": .05, "cadence_10pct": .10}[task_name]
            metrics = _cadence_task(ctx, cfg, run_dir, timing, cadence)
        elif task_name == "serving_save_load":
            metrics = _synchronized_and_failure_task(ctx, cfg, run_dir, timing, failure_only=False)
        else:
            metrics = _synchronized_and_failure_task(ctx, cfg, run_dir, timing, failure_only=False)
        write_json(run_dir / "systems_metrics.json", metrics)
        write_json(run_dir / "timing.json", {"records": timing, "exclusive": "unverified",
                                               "performance_claim": False})
        summary.update(compute_status="COMPUTE_DONE", correctness_gate="PASS", metrics=metrics)
    except Exception as exc:
        summary.update(error_type=type(exc).__name__, reason=str(exc))
        write_json(run_dir / "systems_metrics.json", {"status": "FAILED", "reason": summary["reason"]})
        write_json(run_dir / "timing.json", {"records": timing, "performance_claim": False})
    return finalize_run(run_dir, summary, cfg, root)


def _find_verified_task(state, prefix, source_revision=None):
    matches = []
    for identifier, record in state.get("tasks", {}).items():
        if (identifier.startswith(prefix) and record.get("status") == "COMPUTE_DONE" and
                record.get("sync_status") == "VERIFIED" and record.get("handle_alive") is False and
                (source_revision is None or record.get("spec", {}).get("source_hash") == source_revision)):
            matches.append((identifier, record))
    if not matches:
        raise ValueError(f"E3_DEPENDENCY_REQUIRED: {prefix}")
    return sorted(matches)[-1]


def build_systems_tasks(cfg, root):
    """Build the six compact_v1 E3 tasks behind the verified E2 tail."""
    root = Path(root)
    if cfg.get("experiment", {}).get("run_budget_policy") != RUN_BUDGET_POLICY:
        raise ValueError(f"E3 runner requires run_budget_policy={RUN_BUDGET_POLICY}")
    profiles = load_tuning_profiles(root / cfg["tuning"]["lock_path"])
    core = [(key, value) for key, value in profiles["profiles"].items() if value.get("scope") == "core"]
    if len(core) != 1:
        raise ValueError("E3 requires exactly one frozen core profile")
    profile_hash, profile = core[0]
    state_path = Path(cfg["paths"]["state"]) / "tasks.json"
    if not state_path.exists():
        raise ValueError("E3_DEPENDENCY_REQUIRED: state/tasks.json")
    state = read_json(state_path)
    # Several historical E2 revisions remain in the persistent queue.  Choose
    # the verified revision shared by the largest current E2 chain so an old
    # artifact cannot silently become the systems snapshot.
    from collections import Counter
    revisions = Counter()
    for identifier, record in state.get("tasks", {}).items():
        if (identifier.startswith("E2.") and record.get("status") == "COMPUTE_DONE" and
                record.get("sync_status") == "VERIFIED" and record.get("handle_alive") is False):
            revision = record.get("spec", {}).get("source_hash")
            if revision:
                revisions[revision] += 1
    if not revisions:
        raise ValueError("E3_DEPENDENCY_REQUIRED: no verified E2 source revision")
    e2_revision, count = revisions.most_common(1)[0]
    if count < 20:
        raise ValueError("E3_DEPENDENCY_REQUIRED: verified compact E2 chain is incomplete")
    _, e2_tail = _find_verified_task(
        state, "E2.trec.mapping.residual_mlp.primary.random.m17.", e2_revision)
    _, snapshot_record = _find_verified_task(
        state, "E2.fiqa.scheduler.residual_mlp.primary.random.m17.t101.", e2_revision)
    snapshot_run = Path(snapshot_record["run_dir"]).relative_to(root / cfg["paths"]["runs"]).as_posix()
    q_tune = "cache/vectors/queries/3d569f3c6c2020e9e029032f3ed7b537db3b4c14023e47a1ce54621078e0f6f9/queries.npy"
    common = {
        "config": "configs/experiments/e3.yaml", "phase": "official",
        "measurement_mode": "exclusive", "development_hardware": False,
        "tuning_scope": "core", "input_refs": profile["inputs"],
        "profile_hash": profile_hash, "variant_id": "primary", "overrides": {},
        "resources": {"gpu_device": None, "gpu_memory_gib": 0, "host_ram_gib": 16,
                       "cpu_cores": 8, "disk_scratch_gib": 12, "io_heavy": True},
    }
    tasks = []
    previous = e2_tail["spec"]["task_id"] if e2_tail.get("spec") else None
    for name in E3_TASKS:
        overrides = {
            "experiment": {"profile_hash": profile_hash, "tuning_scope": "core",
                            "system_task": name, "snapshot_run": snapshot_run,
                            "q_tune_cache": q_tune},
            "search": {"backend": "exact" if name == "exact_reference" else "hnsw"},
        }
        identity = {"source_hash": source_hash(root), "profile_hash": profile_hash,
                    "snapshot_run": snapshot_run, "q_tune": q_tune, "task": name,
                    "config": redacted_config({**deepcopy(cfg), "experiment": {
                        **cfg["experiment"], **overrides["experiment"]},
                        "search": {**cfg["search"], **overrides["search"]}})}
        revision = digest(identity)[:12]
        task_id = f"E3.systems.{name}.{revision}"
        deps = [previous] if previous else []
        tasks.append({**common, "task_id": task_id, "experiment": "E3",
                      "config_overrides": overrides, "depends_on": deps, "priority": 80})
        previous = task_id
    return tasks

