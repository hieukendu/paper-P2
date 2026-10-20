"""Persistent single-host subprocess queue; resource admission is conservative."""

from copy import deepcopy
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import psutil
import yaml

from .config import config_hash, load_config, load_tuning_profiles, validate_tuning_profile
from .io import digest, file_lock, read_json, write_json
from .runtime import effective_limits, target_hardware_matches


RESOURCE_KEYS = {"gpu_device", "gpu_memory_gib", "host_ram_gib", "cpu_cores", "disk_scratch_gib", "io_heavy"}
# A cancelled task is a deliberate plan revision, not a scientific result.  It
# is terminal for queue admission, while progress/checklist code still refuses
# to report it as a completed run.
TERMINAL = {"COMPUTE_DONE", "FAILED", "BLOCKED_DATA", "CANCELLED"}


def validate_jobs(jobs):
    by_id = {}
    for task in jobs:
        identifier = task["task_id"]
        if not identifier or Path(identifier).name != identifier or identifier in by_id:
            raise ValueError("Task IDs must be unique path components")
        resources = task["resources"]
        if set(resources) != RESOURCE_KEYS:
            raise ValueError("Explicit complete resource requests are required")
        for key in ("host_ram_gib", "cpu_cores", "disk_scratch_gib"):
            if not math.isfinite(resources[key]) or resources[key] <= 0:
                raise ValueError("RAM/CPU/disk requests must be positive")
        gpu = resources["gpu_device"]
        if gpu is not None and (not isinstance(gpu, int) or isinstance(gpu, bool) or gpu < 0):
            raise ValueError("GPU device must be a visible nonnegative device index")
        memory = resources["gpu_memory_gib"]
        if not math.isfinite(memory) or (gpu is None and memory != 0) or (gpu is not None and memory <= 0):
            raise ValueError("A GPU task requires a positive VRAM reservation")
        if task["phase"] not in {"development", "official"} or task["measurement_mode"] not in {"quality", "exclusive"}:
            raise ValueError("Invalid task phase or measurement mode")
        if not isinstance(task.get("depends_on", []), list):
            raise ValueError("Dependencies must be a list of task IDs")
        by_id[identifier] = task
    visiting, visited = set(), set()
    def visit(identifier):
        if identifier in visiting:
            raise ValueError("Task dependency graph contains a cycle")
        if identifier in visited or identifier not in by_id:
            return  # A prerequisite can be enqueued later.
        visiting.add(identifier)
        for dependency in by_id[identifier].get("depends_on", []):
            visit(dependency)
        visiting.remove(identifier)
        visited.add(identifier)
    for identifier in by_id:
        visit(identifier)
    return jobs


def load_jobs(path):
    document = yaml.safe_load(Path(path).read_text())
    return validate_jobs(document["jobs"] if isinstance(document, dict) else document)


def enqueue_tasks(specs, state_path):
    state_path = Path(state_path)
    with file_lock(state_path.with_suffix(".lock")):
        state = read_json(state_path) if state_path.exists() else {"tasks": {}}
        combined = {key: value["spec"] for key, value in state["tasks"].items()}
        for task in specs:
            existing = combined.get(task["task_id"])
            if existing is not None and digest(existing) != digest(task):
                raise ValueError("An enqueued task is immutable; use a new task ID for a changed config")
            combined[task["task_id"]] = task
        validate_jobs(list(combined.values()))
        for task in specs:
            state["tasks"].setdefault(task["task_id"], {
                "spec": deepcopy(task), "status": "PENDING", "sync_status": "NOT_READY", "reason": None})
        write_json(state_path, state)
        return state


def process_alive(pid, birth_time):
    try:
        process = psutil.Process(pid)
        return (abs(process.create_time() - birth_time) < 1e-3 and process.is_running()
                and process.status() != psutil.STATUS_ZOMBIE)
    except (psutil.NoSuchProcess, psutil.ZombieProcess):
        return False
    except psutil.AccessDenied:
        return None  # An observation failure must never trigger a duplicate worker.


def reconcile_after_restart(state):
    for record in state["tasks"].values():
        if not record.get("pid"):
            continue
        alive = process_alive(record["pid"], record["birth_time"])
        record["handle_alive"] = alive
        signal = Path(record.get("compute_path", "/nonexistent-mixindex-status"))
        if alive is not False and signal.exists():
            compute = read_json(signal)
            record.update(status=compute["compute_status"], run_dir=compute["run_dir"], sync_status="UPLOADING")
        if alive is False:
            result = Path(record["result_path"])
            if result.exists():
                outcome = read_json(result)
                record.update(status=outcome["compute_status"], sync_status=outcome.get("sync_status", "PENDING"), result=outcome)
            elif record["status"] == "RUNNING":
                record.update(status="FAILED", reason="WORKER_EXITED_WITHOUT_RESULT; inspect complete checkpoint before resume")
            elif record.get("sync_status") == "UPLOADING":
                record.update(sync_status="PENDING", reason="WORKER_EXITED_DURING_SYNC; retry sync without recompute")
    return state


def probe_capacity(cfg):
    import torch
    limits = effective_limits()
    gpu = {}
    if torch.cuda.is_available():
        for device in range(torch.cuda.device_count()):
            free, total = torch.cuda.mem_get_info(device)
            name = torch.cuda.get_device_name(device)
            gpu[str(device)] = {"free_gib": free / (1 << 30), "total_gib": total / (1 << 30),
                                "target": target_hardware_matches(cfg, {"hardware": {"devices": [
                                    {"name": name, "vram_total_bytes": total}]}})}
    disks = {}
    for key in ("data", "cache", "runs", "staging"):
        path = Path(cfg["paths"][key])
        path.mkdir(parents=True, exist_ok=True)
        disks[str(path.stat().st_dev)] = shutil.disk_usage(path).free / (1 << 30)
    return {"cpu_cores": limits["cpu_cores"], "ram_free_gib": limits["ram_available_bytes"] / (1 << 30),
            "ram_limit_gib": limits["ram_limit_bytes"] / (1 << 30), "gpu": gpu,
            "disk_free_gib": min(disks.values()), "joint_probe_verified": False}


def can_admit(task, running, capacity, tasks, max_compute_jobs=2, cfg=None):
    if not 1 <= max_compute_jobs <= 2:
        raise ValueError("Compute concurrency is capped at two")
    for dependency in task.get("depends_on", []):
        record = tasks.get(dependency, {})
        if record.get("status") != "COMPUTE_DONE":
            return False, f"DEPENDENCY_PENDING:{dependency}"
        # A compute signal is emitted before the worker uploads and verifies
        # its immutable artifact.  Scientific cells must not start in that
        # window: the predecessor is admissible only after remote verification
        # and after its worker handle has exited.
        if record.get("sync_status") != "VERIFIED":
            return False, f"DEPENDENCY_SYNC_PENDING:{dependency}"
        if record.get("handle_alive") is not False:
            return False, f"DEPENDENCY_WORKER_ACTIVE:{dependency}"
    if len(running) >= max_compute_jobs:
        return False, "COMPUTE_SLOTS_FULL"
    if running and (task["measurement_mode"] == "exclusive" or any(
            row["spec"]["measurement_mode"] == "exclusive" for row in running)):
        return False, "EXCLUSIVE_WINDOW"
    request = task["resources"]
    if running and not capacity.get("joint_probe_verified"):
        return False, "JOINT_THROUGHPUT_PROBE_REQUIRED"
    # Unknown per-worker memory observations imply serialization, never optimistic subtraction.
    if any(row.get("observed_ram_gib") is None for row in running):
        return False, "WORKER_MEMORY_OBSERVATION_REQUIRED"
    ram_remaining = sum(max(0, row["spec"]["resources"]["host_ram_gib"] - row["observed_ram_gib"]) for row in running)
    ram_headroom = max(8, 0.1 * capacity["ram_limit_gib"])
    if request["host_ram_gib"] + ram_remaining + ram_headroom > capacity["ram_free_gib"]:
        return False, "RAM_HEADROOM"
    cpu = sum(row["spec"]["resources"]["cpu_cores"] for row in running)
    if cpu + request["cpu_cores"] > capacity["cpu_cores"] - 1:
        return False, "CPU_QUOTA"
    if request["disk_scratch_gib"] + sum(row["spec"]["resources"]["disk_scratch_gib"] for row in running) > capacity["disk_free_gib"]:
        return False, "DISK_RESERVATION"
    if request["gpu_device"] is not None:
        device = capacity["gpu"].get(str(request["gpu_device"]))
        if device is None:
            return False, "GPU_UNAVAILABLE"
        if not task.get("development_hardware") and not device["target"]:
            return False, "BLOCKED_HARDWARE:CONFIGURED_GPU_REQUIRED"
        same_gpu = [row for row in running if row["spec"]["resources"]["gpu_device"] == request["gpu_device"]]
        if any(row.get("observed_gpu_gib") is None for row in same_gpu):
            return False, "GPU_MEMORY_OBSERVATION_REQUIRED"
        remaining = sum(max(0, row["spec"]["resources"]["gpu_memory_gib"] - row["observed_gpu_gib"]) for row in same_gpu)
        if request["gpu_memory_gib"] + remaining + max(4, device["total_gib"] * 0.1) > device["free_gib"]:
            return False, "GPU_HEADROOM"
    if task["phase"] == "official":
        if cfg is None:
            return False, "OFFICIAL_PROFILE_NOT_LOADED"
        try:
            profiles = load_tuning_profiles(Path(task["root"]) / cfg["tuning"]["lock_path"])
            validate_tuning_profile(task, cfg, profiles)
        except ValueError as exc:
            return False, str(exc)
    return True, "READY"


def launch_task(task, cfg):
    path = Path(cfg["paths"]["state"]) / "workers" / task["task_id"]
    path.mkdir(parents=True, exist_ok=True)
    task_file = path / "task.json"
    write_json(task_file, task)
    env = os.environ.copy()
    compute_path = path / "compute.json"
    env["MIXINDEX_WORKER_STATUS_PATH"] = str(compute_path)
    threads = str(max(1, int(task["resources"]["cpu_cores"])))
    for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        env[key] = threads
    with (path / "stdout.log").open("ab") as output:
        process = subprocess.Popen([sys.executable, "-m", "mixindex.cli", "--root", task["root"],
                                     "_worker", "--task-file", str(task_file)], env=env,
                                    cwd=task["root"], stdin=subprocess.DEVNULL, stdout=output,
                                    stderr=subprocess.STDOUT, shell=False)
    return {"pid": process.pid, "birth_time": psutil.Process(process.pid).create_time(),
            "result_path": str(path / "result.json"), "compute_path": str(compute_path),
            "worker_log": str(path / "stdout.log")}, process


def prepare_task(task, root):
    from .experiments import source_hash
    task = deepcopy(task)
    task["root"] = str(Path(root).resolve())
    cfg = load_config(task["config"], overrides=task.get("config_overrides"), root=root)
    task.setdefault("phase", cfg["execution"]["phase"])
    task.setdefault("depends_on", [])
    task.setdefault("measurement_mode", "quality")
    task["config_hash"] = config_hash(cfg)
    task["source_hash"] = source_hash(root)
    return task


def run_single(task, root):
    from .experiments import run_core_smoke, run_e0, run_e1, run_encoder_probes, run_presetup, source_hash
    cfg = load_config(task["config"], overrides=task.get("config_overrides"), root=root)
    if config_hash(cfg) != task["config_hash"] or source_hash(root) != task["source_hash"]:
        raise ValueError("Task config/source changed after enqueue; enqueue a new task revision")
    if task["phase"] != cfg["execution"]["phase"]:
        raise ValueError("Task phase differs from resolved config")
    if task["experiment"] in {"E0", "E1", "CORE_SMOKE", "RUNTIME_PROBE", "T0", "E2_PREFLIGHT"} and task["phase"] != "development":
        raise ValueError("Development runs cannot be labeled official")
    gpu_stage = task["experiment"] not in {"DATA_PREP", "MODEL_DOWNLOAD"}
    if gpu_stage and cfg["execution"]["device"].startswith("cuda") and task["resources"]["gpu_device"] is None:
        raise ValueError("CUDA execution needs an explicit GPU reservation")
    if cfg["search"]["threads"] > max(1, int(task["resources"]["cpu_cores"])):
        raise ValueError("Search thread count exceeds the task CPU reservation")
    tasks_path = Path(cfg["paths"]["state"]) / "tasks.json"
    tasks = read_json(tasks_path)["tasks"]
    for dependency in task["depends_on"]:
        record = tasks.get(dependency, {})
        if (record.get("status") != "COMPUTE_DONE" or
                record.get("sync_status") != "VERIFIED" or
                record.get("handle_alive") is not False):
            raise ValueError("Worker dependency gate has not completed verified sync")
    if task["phase"] == "official":
        validate_tuning_profile(task, cfg, load_tuning_profiles(Path(root) / cfg["tuning"]["lock_path"]))
    if task["experiment"] == "DATA_PREP":
        from .data.prepare import prepare_dataset
        manifest = prepare_dataset(cfg["dataset"]["name"], cfg, root)
        return {"compute_status": "COMPUTE_DONE", "data_release": manifest["release_hash"]}
    if task["experiment"] in {"MODEL_DOWNLOAD", "MODEL_SMOKE"}:
        from .encoders import build_encoder, model_specs, resolve_model, smoke_encoder
        specs = {role: resolve_model(spec, cfg["paths"], root)
                 for role, spec in model_specs(cfg["models"]["pair"], root).items()}
        result = {role: {"repo_id": spec["repo_id"], "revision": spec["resolved_revision"]}
                  for role, spec in specs.items()}
        if task["experiment"] == "MODEL_SMOKE":
            from .data.prepare import open_validated_data
            from .runtime import probe_hardware, require_target_hardware
            if not task.get("development_hardware"):
                require_target_hardware(cfg, probe_hardware())
            store = open_validated_data(cfg["dataset"]["name"], cfg)
            texts = [d.text for d in store.get_documents([0, len(store) // 2, len(store) - 1])]
            for role, spec in specs.items():
                encoder = build_encoder(spec, cfg["execution"]["device"], cfg["models"]["batch_size"])
                try:
                    result[role]["smoke"] = smoke_encoder(encoder, texts)
                finally:
                    encoder.close()
            path = Path(cfg["paths"]["state"]) / f"model-smoke-{cfg['dataset']['name']}-{cfg['models']['pair']}.json"
            write_json(path, result)
        return {"compute_status": "COMPUTE_DONE", "models": result}
    if task["experiment"] == "E0":
        return run_e0(cfg, root, task.get("development_hardware", False))
    if task["experiment"] == "E1":
        return run_e1(cfg, root, task.get("development_hardware", False))
    if task["experiment"] == "CORE_SMOKE":
        return run_core_smoke(cfg, root, task.get("development_hardware", False))
    if task["experiment"] == "RUNTIME_PROBE":
        return run_encoder_probes(cfg, root, cfg["models"]["pair"], cfg["dataset"]["name"],
                                  cfg["execution"]["device"], task.get("development_hardware", False))
    if task["experiment"] == "T0":
        return run_presetup(task, {}, cfg)
    if task["experiment"] in {"E2_PREFLIGHT", "E2"}:
        from .experiments_static import run_static_cell, run_static_preflight
        return (run_static_preflight if task["experiment"] == "E2_PREFLIGHT" else run_static_cell)(cfg, root)
    raise NotImplementedError("This experiment branch has not yet been integrated")


def run_queue(cfg, root, max_compute_jobs=1, once=False, only_task_ids=None):
    state_path = Path(cfg["paths"]["state"]) / "tasks.json"
    processes = {}
    # One parent owns admission. enqueue uses a separate short lock and can run concurrently.
    with file_lock(state_path.with_suffix(".queue.lock")):
        while True:
            with file_lock(state_path.with_suffix(".lock")):
                state = read_json(state_path) if state_path.exists() else {"tasks": {}}
                reconcile_after_restart(state)
                records = state["tasks"]
                for identifier, process in list(processes.items()):
                    if process.poll() is not None:
                        del processes[identifier]
                alive = [row for row in records.values() if row.get("handle_alive") is not False and row.get("pid")]
                pending = [row for key, row in records.items() if row["status"] == "PENDING"
                           and (only_task_ids is None or key in only_task_ids)]
                active = [row for row in alive if row["status"] == "RUNNING"]
                capacity = probe_capacity(cfg)
                for row in sorted(pending, key=lambda r: (-r["spec"].get("priority", 0), r["spec"]["task_id"])):
                    task = row["spec"]
                    failed_dependencies = [dep for dep in task.get("depends_on", [])
                                           if records.get(dep, {}).get("status") in {"FAILED", "BLOCKED_DATA"}]
                    if failed_dependencies:
                        row.update(status="FAILED", reason="DEPENDENCY_FAILED:" + ",".join(failed_dependencies))
                        continue
                    task_cfg = load_config(task["config"], overrides=task.get("config_overrides"), root=root)
                    allowed, reason = can_admit(task, active, capacity, records, max_compute_jobs, task_cfg)
                    if config_hash(task_cfg) != task["config_hash"]:
                        allowed, reason = False, "CONFIG_CHANGED_AFTER_ENQUEUE"
                    if task["experiment"] not in {"DATA_PREP", "MODEL_DOWNLOAD", "MODEL_SMOKE", "E0",
                                                  "E1", "CORE_SMOKE", "RUNTIME_PROBE", "T0", "E2_PREFLIGHT", "E2"}:
                        allowed, reason = False, "STAGE_NOT_IMPLEMENTED"
                    if task["measurement_mode"] == "exclusive" and alive:
                        allowed, reason = False, "WAITING_FOR_WORKER_AND_UPLOAD_DRAIN"
                    row["reason"] = reason
                    if allowed:
                        handle, process = launch_task(task, cfg)
                        row.update(**handle, status="RUNNING", handle_alive=True)
                        processes[task["task_id"]] = process
                        active.append(row)
                        alive.append(row)
                write_json(state_path, state)
                selected = [row for key, row in records.items() if only_task_ids is None or key in only_task_ids]
                done = all(row["status"] in TERMINAL and not row.get("handle_alive") for row in selected)
            if done or once:
                return state
            time.sleep(5)
