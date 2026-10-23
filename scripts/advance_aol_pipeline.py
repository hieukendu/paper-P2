"""Advance AOL preparation only after the real recovery completion marker."""

from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "state"
LOG = STATE / "aol-pipeline.log"
PROGRESS = STATE / "aol-pipeline-progress.json"


def _now():
    return datetime.now(timezone.utc).isoformat()


def _write_progress(stage, status, **extra):
    payload = {"updated_at": _now(), "stage": stage, "status": status, **extra}
    PROGRESS.parent.mkdir(parents=True, exist_ok=True)
    PROGRESS.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _log(message):
    line = f"{_now()} {message}"
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as stream:
        stream.write(line + "\n")
    print(line, flush=True)


def _recovery_status():
    root = ROOT / "data/raw/aol-ia"
    paths = (root / "downloaded_docs_http", root / "downloaded_docs")
    status = []
    for path in paths:
        if not path.exists():
            continue
        done_file = path / "done_ids.txt"
        status.append({"directory": path.name,
                       "done_ids": sum(1 for _ in done_file.open()) if done_file.exists() else 0,
                       "complete": (path / "_done").exists()})
    return status


def _cli(*args):
    return [sys.executable, "-m", "mixindex.cli", "--root", str(ROOT), *args]


def _run(label, command):
    _write_progress(label, "RUNNING", command=command)
    _log(f"START {label}")
    with LOG.open("a") as stream:
        process = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True, bufsize=1)
        for line in process.stdout:
            stream.write(f"{_now()} {label} {line.rstrip()}\n")
            stream.flush()
        result = process.wait()
    status = "PASS" if result == 0 else "FAIL"
    _write_progress(label, status, exit_code=result)
    _log(f"END {label} status={status} exit_code={result}")
    return result == 0


def _verified_case_t0():
    path = STATE / "tasks.json"
    if not path.exists():
        return False
    payload = json.loads(path.read_text())
    for record in payload.get("tasks", {}).values():
        spec = record.get("spec", {})
        if (spec.get("experiment") == "T0" and
                spec.get("tuning_scope") == "case.aol-ia.arctic" and
                record.get("status") == "COMPUTE_DONE" and
                record.get("sync_status") == "VERIFIED" and
                record.get("handle_alive") is False):
            return True
    return False


def _enqueue_and_run_e6():
    sys.path.insert(0, str(ROOT / "src"))
    from mixindex.config import load_config
    from mixindex.queue import enqueue_tasks, prepare_task, run_queue

    jobs_path = ROOT / "configs/jobs-e6.yaml"
    import yaml
    jobs = yaml.safe_load(jobs_path.read_text())["jobs"]
    config = load_config(root=ROOT)
    specs = [prepare_task(job, ROOT) for job in jobs]
    enqueue_tasks(specs, Path(config["paths"]["state"]) / "tasks.json")
    task_ids = {job["task_id"] for job in jobs}
    _write_progress("e6_queue", "RUNNING", task_ids=sorted(task_ids))
    state = run_queue(config, ROOT, max_compute_jobs=1, only_task_ids=task_ids)
    records = {key: {field: value.get(field)
                     for field in ("status", "sync_status", "reason", "handle_alive")}
               for key, value in state["tasks"].items() if key in task_ids}
    _write_progress("e6_queue", "DONE", tasks=records)
    _log("E6 queue returned; inspect task records before any E7 admission")
    return all(row["status"] == "COMPUTE_DONE" and row["sync_status"] == "VERIFIED"
               and row["handle_alive"] is False for row in records.values())


def main():
    _log("AOL gated advance worker started")
    last_report = 0.0
    while True:
        status = _recovery_status()
        complete = [row for row in status if row["complete"]]
        if complete:
            _log(f"Recovery complete markers: {complete}")
            break
        now = time.monotonic()
        if now - last_report >= 300:
            _log(f"Waiting for recovery: {status}")
            last_report = now
        time.sleep(60)

    if not _run("data_prepare", _cli("data", "prepare", "--dataset", "aol-ia",
                                      "--config", "configs/base.yaml")):
        return 1
    if not _run("data_validate", _cli("data", "validate", "--dataset", "aol-ia",
                                       "--config", "configs/base.yaml")):
        return 1
    # Dataset publication is independent of scientific task admission.  Keep
    # the local validated release if Hub access is temporarily pending.
    _run("data_publish", _cli("data", "publish", "--dataset", "aol-ia",
                              "--config", "configs/base.yaml"))
    if not _verified_case_t0():
        if not _run("t0_case", _cli("presetup", "--scope", "case.aol-ia.arctic",
                                     "--config", "configs/base.yaml")):
            return 1
    if not _verified_case_t0():
        _log("T0.case is not COMPUTE_DONE+SYNC_VERIFIED; E6 remains closed")
        return 1
    if not _run("e6_plan", _cli("plan", "--experiment", "E6",
                                 "--config", "configs/experiments/e6.yaml",
                                 "--output", "configs/jobs-e6.yaml")):
        return 1
    if not _enqueue_and_run_e6():
        _log("E6 did not fully pass compute+sync gates; E7 remains closed")
        return 1
    _log("E6 passed all required task gates; E7 remains intentionally unopened")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
