from pathlib import Path

import pytest
import requests
from huggingface_hub.errors import HfHubHTTPError

from mixindex import hf_sync
from mixindex.config import load_config
from mixindex.io import read_json, write_json


def test_account_quota_does_not_retry_or_allocate_repositories():
    calls = []
    response = requests.Response()
    response.status_code = 403
    def fail():
        calls.append(1)
        raise HfHubHTTPError("Storage quota exceeded", response=response)
    with pytest.raises(hf_sync.SyncError) as failure:
        hf_sync._retry(fail, 3)
    assert failure.value.status == "QUOTA_ERROR"
    assert len(calls) == 1


def test_failed_verification_has_no_completed_marker_and_retries_same_destination(tmp_path, monkeypatch):
    cfg = load_config()
    cfg["paths"] = {key: str(tmp_path / key) for key in cfg["paths"]}
    run = Path(cfg["paths"]["runs"]) / "r1"
    run.mkdir(parents=True)
    write_json(run / "config.lock.json", {"phase": "development"})
    write_json(run / "summary.json", {"compute_status": "COMPUTE_DONE"})
    seen = []
    monkeypatch.setattr(hf_sync, "get_hf_client", lambda root: (object(), "fixture-user"))
    def upload(api, destinations, bundle, cfg):
        seen.append(destinations)
        return destinations
    monkeypatch.setattr(hf_sync, "upload_bundle", upload)
    def fail_verify(api, receipt, manifest):
        raise hf_sync.SyncError("VERIFY_ERROR", "Checksum mismatch")
    monkeypatch.setattr(hf_sync, "verify_remote_bundle", fail_verify)
    first = hf_sync.auto_sync_experiment(run, cfg["sync"], tmp_path, cfg["paths"])
    second = hf_sync.auto_sync_experiment(run, cfg["sync"], tmp_path, cfg["paths"])
    assert first["status"] == second["status"] == "VERIFY_ERROR"
    assert seen[0] == seen[1]
    registry = read_json(Path(cfg["paths"]["state"]) / "hf_repos.json")
    assert len(registry["repos"]) == 1
    assert not list(tmp_path.rglob("COMPLETED.json"))


def test_source_snapshot_closes_before_run_and_is_never_overwritten(tmp_path):
    root, run = tmp_path / "root", tmp_path / "run"
    (root / "src").mkdir(parents=True)
    source = root / "src/example.py"
    source.write_text("value = 1\n")
    hf_sync.snapshot_source(root, run)
    source.write_text("value = 2\n")
    hf_sync.snapshot_source(root, run)
    assert (run / "source/src/example.py").read_text() == "value = 1\n"


def test_transient_connection_failures_have_bounded_retries(monkeypatch):
    calls = []
    monkeypatch.setattr(hf_sync.time, "sleep", lambda seconds: None)
    def fail():
        calls.append(1)
        raise requests.exceptions.ConnectionError("offline")
    with pytest.raises(hf_sync.SyncError) as failure:
        hf_sync._retry(fail, 3)
    assert failure.value.status == "RETRYABLE_ERROR"
    assert len(calls) == 3
