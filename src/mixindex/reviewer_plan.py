"""Frozen reviewer protocol and supplemental task builder.

The reviewer reruns use several standalone scientific runners because their
inputs and checkpoint formats differ.  This module is the single inventory for
those runners: the YAML lists every cell, its two seeds, reuse/parent decision,
gate, and expected outputs.  It deliberately only plans work; it never starts
an expensive worker implicitly.
"""

from __future__ import annotations

from collections import Counter
import hashlib
from pathlib import Path

import yaml

from .io import atomic_bytes, file_digest


REQUIRED_ACTIONS = tuple(f"REV-{index:02d}" for index in range(1, 10))
ALLOWED_MODES = {"run", "analysis", "benchmark", "feasibility", "sync_reconcile"}
ALLOWED_STATUSES = {"planned", "completed", "conditional", "missing_artifact", "excluded", "no_action"}
REQUIRED_CELL_KEYS = {
    "cell_id", "review_action", "subgroup", "mode", "dataset", "pair", "method", "direction",
    "variant", "scheduler", "map_seed", "traffic_seed", "budget_checkpoints", "parent_run_id",
    "reuse", "expected_outputs", "gate", "status",
}


def _read(path: Path) -> dict:
    path = Path(path)
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"Reviewer protocol is not a mapping: {path}")
    return document


def load_protocol(path: Path | str) -> dict:
    path = Path(path)
    document = _read(path)
    validate_protocol(document)
    return document


def validate_protocol(document: dict) -> dict:
    study = document.get("study")
    if not isinstance(study, dict):
        raise ValueError("Reviewer protocol needs a study mapping")
    if study.get("study_id") != "reviewer_v1":
        raise ValueError("Reviewer protocol study_id must be reviewer_v1")
    if not study.get("branch") or not study.get("base_sha"):
        raise ValueError("Reviewer protocol must record one branch and its base SHA")
    if study.get("corpus_expansion") != "EXCLUDED":
        raise ValueError("Reviewer protocol must explicitly exclude corpus expansion")

    cells = document.get("cells")
    if not isinstance(cells, list) or not cells:
        raise ValueError("Reviewer protocol needs explicit cells")
    expected_counts = document.get("expected_cell_counts")
    if not isinstance(expected_counts, dict):
        raise ValueError("Reviewer protocol needs expected_cell_counts")

    identifiers = set()
    scientific_keys = set()
    counts = Counter()
    for cell in cells:
        if not isinstance(cell, dict) or not REQUIRED_CELL_KEYS.issubset(cell):
            missing = sorted(REQUIRED_CELL_KEYS.difference(cell if isinstance(cell, dict) else {}))
            raise ValueError(f"Reviewer cell is missing keys: {missing}")
        cell_id = str(cell["cell_id"])
        if cell_id in identifiers:
            raise ValueError(f"Duplicate reviewer cell_id: {cell_id}")
        identifiers.add(cell_id)
        action = str(cell["review_action"])
        if action not in REQUIRED_ACTIONS:
            raise ValueError(f"Cell {cell_id} has unsupported review action {action}")
        counts[action] += 1
        if cell["mode"] not in ALLOWED_MODES:
            raise ValueError(f"Cell {cell_id} has unsupported mode {cell['mode']}")
        if cell["status"] not in ALLOWED_STATUSES:
            raise ValueError(f"Cell {cell_id} has unsupported status {cell['status']}")
        if not isinstance(cell["reuse"], bool):
            raise ValueError(f"Cell {cell_id} reuse must be boolean")
        if cell["reuse"] and not cell["parent_run_id"]:
            raise ValueError(f"Reused cell {cell_id} needs a parent_run_id")
        if not isinstance(cell["budget_checkpoints"], list) or not cell["budget_checkpoints"]:
            raise ValueError(f"Cell {cell_id} needs budget checkpoints")
        if not isinstance(cell["expected_outputs"], list) or not cell["expected_outputs"]:
            raise ValueError(f"Cell {cell_id} needs expected outputs")
        if cell["map_seed"] not in {17, 29, 43}:
            raise ValueError(f"Cell {cell_id} has an undeclared map seed")
        if cell["traffic_seed"] not in {101, 103, 109}:
            raise ValueError(f"Cell {cell_id} has an undeclared traffic seed")
        signature = tuple(cell[key] for key in (
            "review_action", "subgroup", "dataset", "pair", "method", "direction", "variant", "scheduler",
            "map_seed", "traffic_seed", "mode"))
        if signature in scientific_keys:
            raise ValueError(f"Duplicate scientific reviewer cell: {cell_id}")
        scientific_keys.add(signature)

    expected = {str(key): int(value) for key, value in expected_counts.items()}
    if set(expected) != set(REQUIRED_ACTIONS):
        raise ValueError("expected_cell_counts must cover exactly REV-01 through REV-09")
    actual = {action: counts[action] for action in REQUIRED_ACTIONS}
    if actual != expected:
        raise ValueError(f"Reviewer cell count mismatch: expected={expected}, actual={actual}")

    controls = document.get("controls", {})
    if controls.get("rbo_p") != 0.9 or controls.get("bootstrap_draws") != 10000:
        raise ValueError("Reviewer controls must keep RBO p=0.9 and 10,000 draws")
    if controls.get("primary_access_fraction") != 0.10:
        raise ValueError("Reviewer primary access endpoint must be 10 percent")
    return {"study_id": study["study_id"], "cell_count": len(cells), "counts": actual,
            "corpus_expansion": study["corpus_expansion"],
            "source_allowlist": list(document.get("source_allowlist", []))}


def build_tasks(protocol: dict, protocol_path: Path | str) -> list[dict]:
    validate_protocol(protocol)
    protocol_path = Path(protocol_path)
    protocol_digest = file_digest(protocol_path)
    tasks = []
    for cell in protocol["cells"]:
        tasks.append({
            "task_id": cell["cell_id"],
            "experiment": "REVIEWER",
            "phase": "analysis" if cell["mode"] in {"analysis", "benchmark"} else "official",
            "review_action": cell["review_action"],
            "mode": cell["mode"],
            "config": str(protocol_path),
            "protocol_sha256": protocol_digest,
            "cell": cell,
            "depends_on": list(cell.get("depends_on", [])),
            "resources": cell.get("resources", {}),
        })
    if len({task["task_id"] for task in tasks}) != len(tasks):
        raise ValueError("Reviewer task IDs are not unique")
    return tasks


def write_jobs(protocol_path: Path | str, output: Path | str) -> dict:
    protocol_path = Path(protocol_path)
    output = Path(output)
    protocol = load_protocol(protocol_path)
    tasks = build_tasks(protocol, protocol_path)
    payload = {
        "protocol": {
            "path": str(protocol_path),
            "sha256": file_digest(protocol_path),
            "summary": validate_protocol(protocol),
        },
        "jobs": tasks,
    }
    atomic_bytes(output, yaml.safe_dump(payload, sort_keys=False).encode("utf-8"))
    return {"output": str(output), "protocol_sha256": payload["protocol"]["sha256"],
            "tasks": len(tasks), "counts": payload["protocol"]["summary"]["counts"]}


def protocol_digest(path: Path | str) -> str:
    """Return a byte digest without exposing protocol contents or credentials."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()
