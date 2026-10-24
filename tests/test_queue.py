from copy import deepcopy
import os

import psutil
import pytest

from mixindex.io import read_json, write_json
from mixindex.queue import can_admit, enqueue_tasks, process_alive, reconcile_after_restart, run_queue


def job(identifier="one", gpu=0):
    return {"task_id": identifier, "experiment": "E1", "config": "configs/experiments/e1.yaml",
            "phase": "development", "measurement_mode": "quality", "depends_on": [],
            "development_hardware": True,
            "resources": {"gpu_device": gpu, "gpu_memory_gib": 4 if gpu is not None else 0,
                          "host_ram_gib": 8, "cpu_cores": 4, "disk_scratch_gib": 2,
                          "io_heavy": False}}


def capacity():
    return {"cpu_cores": 16, "ram_free_gib": 70, "ram_limit_gib": 100, "disk_free_gib": 100,
            "joint_probe_verified": True, "gpu": {"0": {"free_gib": 30, "total_gib": 80, "target": False}}}


def test_dynamic_enqueue_preserves_live_jobs_and_checks_combined_graph(tmp_path):
    path = tmp_path / "tasks.json"
    enqueue_tasks([job()], path)
    state = read_json(path)
    state["tasks"]["one"]["status"] = "RUNNING"
    write_json(path, state)
    enqueue_tasks([job("two")], path)
    assert read_json(path)["tasks"]["one"]["status"] == "RUNNING"
    changed = job()
    changed["resources"]["host_ram_gib"] = 9
    with pytest.raises(ValueError, match="immutable"):
        enqueue_tasks([changed], path)
    first, second = job("a"), job("b")
    first["depends_on"] = ["b"]
    second["depends_on"] = ["a"]
    enqueue_tasks([first], tmp_path / "cycle.json")
    with pytest.raises(ValueError, match="cycle"):
        enqueue_tasks([second], tmp_path / "cycle.json")


def test_admission_uses_effective_limits_remaining_reservations_and_headroom():
    request = job("two")
    running = [{"spec": job(), "observed_ram_gib": 6, "observed_gpu_gib": 3}]
    assert can_admit(request, running, capacity(), {}, 2) == (True, "READY")
    missing = deepcopy(running)
    missing[0]["observed_ram_gib"] = None
    assert can_admit(request, missing, capacity(), {}, 2)[1] == "WORKER_MEMORY_OBSERVATION_REQUIRED"
    # Free-now already includes existing allocations: charge only unused reservation.
    constrained = capacity()
    constrained["ram_free_gib"] = 21
    assert can_admit(request, running, constrained, {}, 2)[0]
    constrained["ram_free_gib"] = 19
    assert can_admit(request, running, constrained, {}, 2)[1] == "RAM_HEADROOM"
    constrained = capacity()
    constrained["cpu_cores"] = 8
    assert can_admit(request, running, constrained, {}, 2)[1] == "CPU_QUOTA"
    with pytest.raises(ValueError, match="two"):
        can_admit(request, [], capacity(), {}, 3)


def test_exclusive_jobs_dependencies_target_and_joint_probe_are_independent():
    request, existing = job("two"), {"spec": job(), "observed_ram_gib": 6, "observed_gpu_gib": 3}
    request["measurement_mode"] = "exclusive"
    assert can_admit(request, [existing], capacity(), {}, 2)[1] == "EXCLUSIVE_WINDOW"
    request["measurement_mode"] = "quality"
    request["depends_on"] = ["T0.core"]
    assert can_admit(request, [], capacity(), {}, 2)[1].startswith("DEPENDENCY_PENDING")
    assert can_admit(request, [], capacity(), {"T0.core": {
        "status": "COMPUTE_DONE", "sync_status": "PENDING", "handle_alive": False}}, 2)[1].startswith("DEPENDENCY_SYNC_PENDING")
    assert can_admit(request, [], capacity(), {"T0.core": {
        "status": "COMPUTE_DONE", "sync_status": "VERIFIED", "handle_alive": False}}, 2)[0]
    request["depends_on"] = []
    request["development_hardware"] = False
    assert "BLOCKED_HARDWARE" in can_admit(request, [], capacity(), {}, 2)[1]
    request["development_hardware"] = True
    unknown = capacity()
    unknown["joint_probe_verified"] = False
    assert can_admit(request, [existing], unknown, {}, 2)[1] == "JOINT_THROUGHPUT_PROBE_REQUIRED"


def test_validated_setup_dependency_does_not_require_artifact_upload():
    request = job("smoke")
    request["depends_on"] = ["data"]
    setup = job("data", gpu=None)
    setup["experiment"] = "DATA_PREP"
    records = {"data": {"spec": setup, "status": "COMPUTE_DONE",
                         "sync_status": "PENDING", "handle_alive": False}}
    assert can_admit(request, [], capacity(), records, 2)[0]


def test_scientific_dependency_still_requires_verified_upload():
    request = job("cell")
    request["depends_on"] = ["smoke"]
    smoke = job("smoke", gpu=0)
    smoke["experiment"] = "E1"
    records = {"smoke": {"spec": smoke, "status": "COMPUTE_DONE",
                          "sync_status": "PENDING", "handle_alive": False}}
    assert can_admit(request, [], capacity(), records, 2)[1] == "DEPENDENCY_SYNC_PENDING:smoke"


def test_pid_birth_time_and_compute_signal_prevent_duplicate_restarts(tmp_path):
    pid = os.getpid()
    birth = psutil.Process(pid).create_time()
    assert process_alive(pid, birth)
    assert not process_alive(pid, birth - 10)
    result = tmp_path / "result.json"
    signal = tmp_path / "compute.json"
    write_json(signal, {"compute_status": "COMPUTE_DONE", "run_dir": str(tmp_path / "run")})
    state = {"tasks": {"one": {"spec": job(), "status": "RUNNING", "pid": pid,
                                 "birth_time": birth, "result_path": str(result), "compute_path": str(signal)}}}
    reconciled = reconcile_after_restart(state)["tasks"]["one"]
    assert reconciled["status"] == "COMPUTE_DONE" and reconciled["handle_alive"] is True
    assert reconciled["sync_status"] == "UPLOADING"


def test_dead_worker_keeps_compute_and_marks_sync_pending(tmp_path):
    state = {"tasks": {"one": {"spec": job(), "status": "COMPUTE_DONE", "pid": os.getpid(),
                                 "birth_time": psutil.Process().create_time() - 10,
                                 "result_path": str(tmp_path / "result.json"), "sync_status": "UPLOADING"}}}
    reconciled = reconcile_after_restart(state)["tasks"]["one"]
    assert reconciled["status"] == "COMPUTE_DONE" and reconciled["sync_status"] == "PENDING"


def test_failed_dependency_finishes_queue_without_launching_a_worker(tmp_path, monkeypatch):
    from mixindex.config import load_config
    import mixindex.queue as queue
    cfg = load_config()
    cfg["paths"] = {key: str(tmp_path / key) for key in cfg["paths"]}
    first, second = job("one"), job("two")
    second["depends_on"] = ["one"]
    path = tmp_path / "state/tasks.json"
    state = enqueue_tasks([first, second], path)
    state["tasks"]["one"]["status"] = "FAILED"
    write_json(path, state)
    monkeypatch.setattr(queue, "probe_capacity", lambda cfg: capacity())
    def forbidden(*args):
        raise AssertionError("Failed dependency launched a worker")
    monkeypatch.setattr(queue, "launch_task", forbidden)
    result = run_queue(cfg, tmp_path)
    assert result["tasks"]["two"]["status"] == "FAILED"
    assert result["tasks"]["two"]["reason"] == "DEPENDENCY_FAILED:one"
