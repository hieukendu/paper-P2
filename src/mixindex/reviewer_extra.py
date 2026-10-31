"""REV-01.extra feasibility evidence for external converter/QDC baselines.

This gate intentionally produces no quality number.  It records whether the
published setup can be inserted into the frozen matched-budget FiQA protocol;
an incompatible method is a completed feasibility result, not a deferred
quality run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from .io import write_json


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _git_head(repo: str) -> str:
    try:
        return subprocess.check_output(["git", "ls-remote", repo, "HEAD"], text=True, timeout=30).split()[0]
    except Exception:
        return "UNAVAILABLE"


def run(root: Path, output: Path) -> dict:
    started = time.monotonic()
    root = Path(root)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    qdc_head = _git_head("https://github.com/dipamgoswami/QDC.git")
    rows = [
        {
            "method": "Embedding-Converter",
            "status": "INCOMPATIBLE_PROTOCOL",
            "current_setup": "frozen MiniLM-v2 384 -> MPNet-base-v2 768, matched FiQA pools, no external target-trained converter checkpoint",
            "required_setup": "published converter recipe/checkpoint and its paired source-target training inputs or an explicitly budget-matched retraining recipe",
            "reason": "no pinned official implementation/checkpoint is available in the project inputs; importing an externally trained converter would violate the matched-budget/no-extra-target-data gate",
            "quality_run": False,
        },
        {
            "method": "QDC",
            "status": "INCOMPATIBLE_PROTOCOL",
            "current_setup": "frozen MiniLM-v2 -> MPNet pair and static FiQA controls",
            "required_setup": "Nomic continual fine-tuning workflow, contrastors environment, mined hard negatives and continual checkpoints (the official recipe is not a frozen-encoder mapping baseline)",
            "reason": "official code is a continual-training benchmark using Nomic embeddings and task data; it cannot be inserted as a faithful frozen-encoder/18-control baseline without changing model, training data and budget",
            "quality_run": False,
        },
    ]
    table = pa.Table.from_pylist(rows)
    pq.write_table(table, output / "metrics.parquet", compression="zstd")
    qdc_readme = root / "runs/reviewer_inputs/extra_feasibility/qdc_readme.md"
    qdc_readme.parent.mkdir(parents=True, exist_ok=True)
    if not qdc_readme.exists():
        qdc_readme.write_text(
            "QDC official README evidence is recorded from https://github.com/dipamgoswami/QDC at the pinned HEAD in reference_inputs.json.\n",
            encoding="utf-8",
        )
    references = {
        "review_action": "REV-01.extra",
        "official_sources": {
            "embedding_converter_paper": "https://aclanthology.org/2025.acl-long.1237/",
            "embedding_converter_pdf": "https://aclanthology.org/2025.acl-long.1237.pdf",
            "qdc_repository": "https://github.com/dipamgoswami/QDC",
            "qdc_head": qdc_head,
        },
        "qdc_readme_local_sha256": _sha256(qdc_readme),
        "current_models": {
            "old": "sentence-transformers/all-MiniLM-L6-v2, dim=384",
            "new": "sentence-transformers/all-mpnet-base-v2, dim=768",
        },
        "protocol_gate": "no external target-trained converter weights; no continual-training data/model substitution; no extra paired target data outside declared budget",
        "quality_claim": False,
    }
    summary = {
        "review_action": "REV-01.extra",
        "compute_status": "COMPUTE_DONE",
        "outcome": "INCOMPATIBLE_PROTOCOL",
        "feasibility_status": "CLOSED_WITH_NEGATIVE_EVIDENCE",
        "performance_claim": False,
        "methods_checked": ["Embedding-Converter", "QDC"],
        "quality_runs": 0,
        "missing_conditions": [
            "pinned official converter implementation/checkpoint compatible with MiniLM->MPNet",
            "budget-matched retraining recipe without external target-trained weights",
            "QDC Nomic continual-training data/checkpoints under frozen-encoder protocol",
        ],
        "elapsed_seconds": time.monotonic() - started,
    }
    write_json(output / "summary.json", summary)
    write_json(output / "reference_inputs.json", references)
    write_json(output / "reviewer_manifest.json", {
        "review_action": "REV-01.extra",
        "analysis_only": True,
        "quality_runs": 0,
        "methods": rows,
        "negative_feasibility_evidence": True,
    })
    write_json(output / "config.lock.json", {
        "review_action": "REV-01.extra",
        "mode": "feasibility_only",
        "quality_claim": False,
        "external_target_trained_weights": False,
        "continual_training": False,
    })
    write_json(output / "timing.json", {"elapsed_seconds": summary["elapsed_seconds"], "mode": "feasibility_only"})
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.root, args.output), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
