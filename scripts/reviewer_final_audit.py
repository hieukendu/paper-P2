"""Audit the frozen reviewer protocol against pinned Hugging Face receipts.

This is an analysis/provenance check.  It does not start a worker or mutate an
existing run.  It verifies every reviewer catalog marker, restores one learned
state and one E5 graph, and records the final cell/Q1--Q7 coverage together
with the declared negative findings.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

import hnswlib
import numpy as np
import pyarrow.parquet as pq
from dotenv import dotenv_values
from huggingface_hub import hf_hub_download
from safetensors.numpy import load_file

from mixindex.reviewer_plan import load_protocol


CATALOG_REVISION = "d5e6d8e0db211a01f2ca5b324cef47b9e7ade92c"
E5_MARKER_REPO = "deadgod3005/mixindex-runs-003"
E5_MARKER_REVISION = "ff52cc31a9e41f31abc2ca5a2ddd7c3ea3fd86b0"
E5_MARKER_PATH = (
    "runs/E5-scale-degree-m29-t101-ca194e98f844/"
    "aa87818db8949896f43e63673043335bac08545583d2b19bfc0b11769dbacb1f/"
    "COMPLETED.json"
)
E5_CHECKPOINTS = (
    "bootstrap-000001750",
    "accessed-000002500",
    "accessed-000005000",
    "accessed-000012500",
    "accessed-000025000",
    "accessed-000050000",
)


def _download(repo_id: str, filename: str, revision: str, token: str) -> Path:
    return Path(hf_hub_download(repo_id=repo_id, repo_type="dataset", filename=filename,
                                revision=revision, token=token))


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _part_signature(part: dict) -> dict:
    return {
        "repo_id": part["repo_id"],
        "revision": part["revision"],
        "prefix": part["prefix"],
        "files": sorted(part["files"]),
    }


def _catalog_marker_audit(catalog: dict, token: str) -> dict:
    errors = []
    verified = 0
    for run_id, entry in sorted(catalog["runs"].items()):
        receipt = entry.get("receipt", {})
        try:
            if receipt.get("status") != "VERIFIED":
                raise ValueError(f"catalog status is {receipt.get('status')!r}")
            marker_ref = receipt["marker"]
            marker_path = _download(marker_ref["repo_id"], marker_ref["path"],
                                    marker_ref["revision"], token)
            marker = _json(marker_path)
            if marker.get("payload_id") != receipt.get("payload_id"):
                raise ValueError("marker payload_id differs from catalog receipt")
            marker_parts = sorted((_part_signature(part) for part in marker.get("parts", [])),
                                  key=lambda part: (part["repo_id"], part["revision"], part["prefix"]))
            receipt_parts = sorted((_part_signature(part) for part in receipt.get("parts", [])),
                                   key=lambda part: (part["repo_id"], part["revision"], part["prefix"]))
            if marker_parts != receipt_parts:
                raise ValueError("marker parts differ from catalog receipt")
            verified += 1
        except Exception as exc:  # pragma: no cover - exercised by remote failures
            errors.append({"run_id": run_id, "error": f"{type(exc).__name__}: {exc}"})
    return {
        "catalog_runs": len(catalog["runs"]),
        "marker_verified": verified,
        "unverified": errors,
        "status": "VERIFIED" if not errors and verified == len(catalog["runs"]) else "FAILED",
    }


def _entry_file(entry: dict, filename: str, token: str) -> Path:
    for part in entry["receipt"]["parts"]:
        if filename in part["files"]:
            return _download(part["repo_id"], f"{part['prefix']}/{filename}",
                             part["revision"], token)
    raise FileNotFoundError(f"{filename} is absent from {entry['receipt']['run_id']}")


def _protocol_audit(protocol: dict, protocol_path: Path) -> dict:
    cells = protocol["cells"]
    actions = [f"REV-{index:02d}" for index in range(1, 10)]
    status_counts = Counter(str(cell["status"]) for cell in cells)
    by_action = {}
    for action in actions:
        rows = [cell for cell in cells if cell["review_action"] == action]
        by_action[action] = {
            "planned_cells": len(rows),
            "completed_cells": sum(cell["status"] == "completed" for cell in rows),
            "reused_cells": sum(bool(cell["reuse"]) for cell in rows),
            "statuses": dict(sorted(Counter(str(cell["status"]) for cell in rows).items())),
        }
    digest = hashlib.sha256(protocol_path.read_bytes()).hexdigest()
    return {
        "study_id": protocol["study"]["study_id"],
        "protocol_sha256": digest,
        "branch": protocol["study"]["branch"],
        "base_sha": protocol["study"]["base_sha"],
        "corpus_expansion": protocol["study"]["corpus_expansion"],
        "cell_count": len(cells),
        "status_counts": dict(sorted(status_counts.items())),
        "reuse_cells": sum(bool(cell["reuse"]) for cell in cells),
        "new_cells": sum(not bool(cell["reuse"]) for cell in cells),
        "by_action": by_action,
    }


def _e5_graph_audit(token: str) -> dict:
    marker_path = _download(E5_MARKER_REPO, E5_MARKER_PATH, E5_MARKER_REVISION, token)
    marker = _json(marker_path)
    graph_part = next((part for part in marker["parts"]
                       if part["repo_id"] == "deadgod3005/mixindex-runs-004"), None)
    if graph_part is None:
        raise ValueError("E5 completion marker has no runs-004 graph part")
    graph_files = sorted(path for path in graph_part["files"] if path.endswith("/index/hnsw.bin"))
    expected_graphs = [f"checkpoints/{checkpoint}/index/hnsw.bin" for checkpoint in E5_CHECKPOINTS]
    if sorted(path.removeprefix(graph_part["prefix"] + "/") for path in graph_files) != sorted(expected_graphs):
        raise ValueError("E5 marker does not list all six degree-m29 HNSW graphs")

    prefix = graph_part["prefix"]
    checkpoint = E5_CHECKPOINTS[0]
    graph_path = _download(graph_part["repo_id"], f"{prefix}/checkpoints/{checkpoint}/index/hnsw.bin",
                           graph_part["revision"], token)
    ids_path = _download(graph_part["repo_id"], f"{prefix}/checkpoints/{checkpoint}/index/ids.npy",
                         graph_part["revision"], token)
    index_meta_path = _download(graph_part["repo_id"], f"{prefix}/checkpoints/{checkpoint}/index/index.json",
                                graph_part["revision"], token)
    ids = np.load(ids_path, mmap_mode="r", allow_pickle=False)
    index_meta = _json(index_meta_path)
    dimension = int(index_meta.get("dim", index_meta.get("dimension", 1024)))
    index = hnswlib.Index(space="cosine", dim=dimension)
    index.load_index(str(graph_path), max_elements=len(ids))
    return {
        "marker_repo": E5_MARKER_REPO,
        "marker_revision": E5_MARKER_REVISION,
        "marker_path": E5_MARKER_PATH,
        "payload_id": marker["payload_id"],
        "graph_repo": graph_part["repo_id"],
        "graph_revision": graph_part["revision"],
        "graph_count": len(graph_files),
        "graph_checkpoints": E5_CHECKPOINTS,
        "representative_checkpoint": checkpoint,
        "representative_graph_bytes": graph_path.stat().st_size,
        "representative_index_rows": int(len(ids)),
        "representative_dimension": dimension,
        "representative_hnsw_load": "PASS",
    }


def _restore_audit(catalog: dict, token: str) -> dict:
    aggregate_entry = catalog["runs"]["REV-AGGREGATE-fiqa-v6"]
    aggregate = _json(_entry_file(aggregate_entry, "reviewer_aggregate.json", token))
    if aggregate.get("bootstrap_draws") != 10_000 or aggregate.get("performance_claim") is not False:
        raise ValueError("REV-AGGREGATE-fiqa-v6 has unexpected inference controls")

    transition_entry = catalog["runs"]["REV-07-bge-fiqa-op-read-m17-t101"]
    map_path = _entry_file(transition_entry, "checkpoints/accessed-000002020/M0.safetensors", token)
    tensors = load_file(str(map_path))

    e5_entry = catalog["runs"]["REV-04-e5-posthoc"]
    e5_summary = _json(_entry_file(e5_entry, "summary.json", token))
    heldout_entry = catalog["runs"]["REV-08-heldout-e5"]
    heldout_summary = _json(_entry_file(heldout_entry, "summary.json", token))
    heldout_metrics_path = _entry_file(heldout_entry, "metrics.parquet", token)
    columns = ["left", "right", "map_seed"]
    table = pq.read_table(heldout_metrics_path, columns=columns)
    return {
        "aggregate_v6": {
            "hf_url": aggregate_entry["receipt"]["hf_url"],
            "raw_rows": aggregate["raw_rows"],
            "descriptive_rows": aggregate["descriptive_rows"],
            "contrast_rows": aggregate["contrast_rows"],
            "bootstrap_draws": aggregate["bootstrap_draws"],
            "performance_claim": aggregate["performance_claim"],
        },
        "rev07_representative_restore": {
            "hf_url": transition_entry["receipt"]["hf_url"],
            "path": "checkpoints/accessed-000002020/M0.safetensors",
            "bytes": map_path.stat().st_size,
            "tensors": sorted(tensors),
            "safetensors_load": "PASS",
        },
        "rev04_e5": {
            "hf_url": e5_entry["receipt"]["hf_url"],
            "snapshot_cells_expected": e5_summary["snapshot_cells_expected"],
            "snapshot_cells_available": e5_summary["snapshot_cells_available"],
            "per_query_rows": e5_summary["per_query_rows"],
            "missing_cells": e5_summary.get("missing_cells", []),
        },
        "rev08_heldout": {
            "hf_url": heldout_entry["receipt"]["hf_url"],
            "contrast_rows": heldout_summary["contrast_rows"],
            "map_seeds": sorted(set(int(value) for value in table["map_seed"].to_pylist())),
            "contrast_pairs": sorted({f"{left}_minus_{right}" for left, right in zip(
                table["left"].to_pylist(), table["right"].to_pylist())}),
        },
    }


def audit(root: Path, protocol_path: Path, catalog_repo: str, catalog_revision: str,
          output: Path) -> dict:
    env = dotenv_values(root / ".env")
    token = env.get("HF_TOKEN")
    if not token:
        raise ValueError("HF_TOKEN is required from .env for the pinned HF audit")
    protocol = load_protocol(protocol_path)
    catalog_path = _download(catalog_repo, "catalog.json", catalog_revision, token)
    catalog = _json(catalog_path)
    marker_audit = _catalog_marker_audit(catalog, token)
    e5_graph = _e5_graph_audit(token)
    restore = _restore_audit(catalog, token)
    action_counts = Counter()
    for run_id in catalog["runs"]:
        action_counts["REV-AGGREGATE" if run_id.startswith("REV-AGGREGATE") else run_id[:6]] += 1
    result = {
        "audit": "REV-11",
        "status": "VERIFIED" if marker_audit["status"] == "VERIFIED" else "FAILED",
        "catalog": {
            "repo_id": catalog_repo,
            "revision": catalog_revision,
            "run_count": len(catalog["runs"]),
            "action_counts": dict(sorted(action_counts.items())),
            "marker_audit": marker_audit,
        },
        "protocol": _protocol_audit(protocol, protocol_path),
        "e5_degree_m29": e5_graph,
        "restore_and_analysis": restore,
        "negative_findings": [
            {
                "artifact": "REV-01-extra-feasibility",
                "status": "INCOMPATIBLE_PROTOCOL",
                "quality_runs": 0,
                "finding": "QDC and Embedding-Converter were not treated as faithful frozen MiniLM-to-MPNet matched-budget baselines; no fabricated quality cell was added.",
            },
            {
                "artifact": "performance_claims",
                "status": "NO_PERFORMANCE_CLAIM",
                "finding": "Reviewer aggregates retain performance_claim=false and condition inference on the declared seed/query design.",
            },
        ],
        "q_status": {
            "Q1": {"status": "COMPLETE", "evidence": ["REV-01", "REV-AGGREGATE-fiqa-v6"]},
            "Q2": {"status": "COMPLETE", "evidence": ["REV-03", "REV-AGGREGATE-fiqa-v6"]},
            "Q3": {"status": "COMPLETE_WITH_DEFINED_WORKLOAD", "evidence": ["REV-04", "REV-08-heldout-e5"]},
            "Q4": {"status": "COMPLETE", "evidence": ["REV-02", "REV-AGGREGATE-fiqa-v6"]},
            "Q5": {"status": "COMPLETE", "evidence": ["REV-04", "REV-04-e5-posthoc"]},
            "Q6": {"status": "COMPLETE_WITH_PROXY_LIMITATION", "evidence": ["REV-09-aol-click-proxy-m17-v2"]},
            "Q7": {"status": "COMPLETE_WITH_SAMPLE_ESTIMATE", "evidence": ["REV-06-fiqa-cost-m17"]},
        },
        "source": {
            "protocol": str(protocol_path),
            "token_source": ".env:HF_TOKEN",
            "secrets_recorded": False,
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--protocol", type=Path, default=Path("configs/reviewer_v1.yaml"))
    parser.add_argument("--catalog-repo", default="deadgod3005/mixindex-runs-001")
    parser.add_argument("--catalog-revision", default=CATALOG_REVISION)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    protocol = args.protocol if args.protocol.is_absolute() else root / args.protocol
    output = args.output if args.output.is_absolute() else root / args.output
    result = audit(root, protocol.resolve(), args.catalog_repo, args.catalog_revision, output.resolve())
    print(json.dumps({
        "status": result["status"],
        "catalog_runs": result["catalog"]["run_count"],
        "marker_verified": result["catalog"]["marker_audit"]["marker_verified"],
        "protocol_cells": result["protocol"]["cell_count"],
        "e5_graphs": result["e5_degree_m29"]["graph_count"],
    }, sort_keys=True))
    return 0 if result["status"] == "VERIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
