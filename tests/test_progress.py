from mixindex.progress import update_checklist


def _read_checklist(root):
    return (root / "checklist.md").read_text()


def test_checklist_keeps_only_compute_and_verified_rows(tmp_path):
    (tmp_path / "checklist.md").write_text(
        "before\n<!-- progress:begin -->\n<!-- progress:end -->\nafter\n"
    )
    task_id = "E7-example"

    update_checklist(tmp_path, task_id, {"compute_status": "RUNNING", "sync_status": "PENDING"})
    assert task_id not in _read_checklist(tmp_path)

    update_checklist(tmp_path, task_id, {"compute_status": "COMPUTE_DONE", "sync_status": "PENDING"})
    assert task_id not in _read_checklist(tmp_path)

    update_checklist(tmp_path, task_id, {
        "compute_status": "COMPUTE_DONE",
        "sync_status": "VERIFIED",
        "outcome": "inconclusive",
        "hf_url": "https://huggingface.co/example",
    })
    text = _read_checklist(tmp_path)
    assert "- [x] E7-example — compute=COMPUTE_DONE; sync=VERIFIED;" in text

    update_checklist(tmp_path, task_id, {"compute_status": "FAILED", "sync_status": "NOT_READY"})
    assert task_id not in _read_checklist(tmp_path)
