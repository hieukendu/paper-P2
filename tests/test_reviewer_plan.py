from pathlib import Path

from mixindex.reviewer_plan import build_tasks, load_protocol, validate_protocol, write_jobs


def test_reviewer_protocol_has_explicit_unique_cells_and_all_gates():
    path = Path("configs/reviewer_v1.yaml")
    protocol = load_protocol(path)
    summary = validate_protocol(protocol)
    assert summary["study_id"] == "reviewer_v1"
    assert summary["cell_count"] == sum(summary["counts"].values())
    assert set(summary["counts"]) == {f"REV-{i:02d}" for i in range(1, 10)}
    tasks = build_tasks(protocol, path)
    assert len(tasks) == summary["cell_count"]
    assert len({task["task_id"] for task in tasks}) == len(tasks)
    assert all(task["cell"]["expected_outputs"] for task in tasks)


def test_reviewer_cli_plan_is_pinned_to_protocol_bytes(tmp_path):
    output = tmp_path / "reviewer_jobs.yaml"
    result = write_jobs(Path("configs/reviewer_v1.yaml"), output)
    assert result["tasks"] > 0
    text = output.read_text(encoding="utf-8")
    assert result["protocol_sha256"] in text
    assert "REV-07.bge_fiqa.OP.read.m17.t101" in text
