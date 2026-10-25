"""Update only stable checklist markers and the managed run block."""

from pathlib import Path
import re

from .io import atomic_bytes, file_lock


def mark_module_complete(project_root, module_id, verification_summary):
    path = Path(project_root) / "checklist.md"
    with file_lock(path.with_suffix(".lock")):
        text = path.read_text()
        pattern = rf"(?m)^- \[[ x]\] {re.escape(module_id)} — (.*)$"
        if not re.search(pattern, text):
            raise ValueError(f"Missing checklist marker {module_id}")
        text = re.sub(pattern, lambda m: f"- [x] {module_id} — {m[1]}", text)
        atomic_bytes(path, text.encode())


def update_checklist(project_root, task_id, result):
    path = Path(project_root) / "checklist.md"
    compute = result["compute_status"]
    sync = result.get("sync_status", "NOT_READY")
    eligible = compute == "COMPUTE_DONE" and sync == "VERIFIED"
    with file_lock(path.with_suffix(".lock")):
        text = path.read_text()
        begin, end = "<!-- progress:begin -->", "<!-- progress:end -->"
        before, rest = text.split(begin, 1)
        block, after = rest.split(end, 1)
        rows = [line for line in block.splitlines() if line.startswith("- [")]
        rows = [line for line in rows if not re.match(rf"^- \[[ x]\] {re.escape(task_id)} —", line)]
        if eligible:
            url = result.get("hf_url", "pending")
            expectation = result.get("expect_classification")
            expectation_text = f"; expect={expectation}" if expectation else ""
            row = (f"- [x] {task_id} — compute={compute}; sync={sync}; "
                   f"outcome={result.get('outcome', 'diagnostic')}{expectation_text}; HF={url}")
            rows.append(row)
        atomic_bytes(path, (before + begin + "\n" + "\n".join(rows) + "\n" + end + after).encode())


def remove_checklist(project_root, task_id):
    """Remove a transient running row without reporting a failed experiment."""
    path = Path(project_root) / "checklist.md"
    with file_lock(path.with_suffix(".lock")):
        text = path.read_text()
        begin, end = "<!-- progress:begin -->", "<!-- progress:end -->"
        before, rest = text.split(begin, 1)
        block, after = rest.split(end, 1)
        rows = [line for line in block.splitlines()
                if not re.match(rf"^- \[[ x]\] {re.escape(task_id)} —", line)]
        payload = "\n".join(rows).strip("\n")
        replacement = before + begin + ("\n" + payload if payload else "") + "\n" + end + after
        atomic_bytes(path, replacement.encode())
