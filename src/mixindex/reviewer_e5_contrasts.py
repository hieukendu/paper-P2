"""REV-08 held-out paired contrasts from the verified REV-04.E5 replay."""

from __future__ import annotations

import argparse
import json
import shutil
import time
from collections import defaultdict
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from .io import file_digest, write_json


CHECKPOINTS = ("bootstrap", "f_0.05", "f_0.10", "f_0.25")
METRICS = ("overlap_at_1", "overlap_at_3", "overlap_at_10", "rbo_ext_10")


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def run(parent: Path, output: Path) -> dict:
    started = time.monotonic()
    parent = Path(parent)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    source = pq.read_table(parent / "metrics.parquet").to_pylist()
    rows = [row for row in source if row.get("role") == "heldout" and row.get("checkpoint") in CHECKPOINTS]
    by_key: dict[tuple[str, int, str, str], dict[str, dict]] = defaultdict(dict)
    for row in rows:
        key = (str(row["query_id"]), int(row["map_seed"]), str(row["checkpoint"]), str(row["metric"] if "metric" in row else ""))
        by_key[key][str(row["scheduler"])] = row
    # Index one row per query/checkpoint/seed; metrics are stored as columns in
    # the parent table, so pair the complete source rows directly.
    source_index: dict[tuple[str, int, str], dict[str, dict]] = defaultdict(dict)
    for row in rows:
        source_index[(str(row["query_id"]), int(row["map_seed"]), str(row["checkpoint"]))][str(row["scheduler"])] = row
    contrast_rows: list[dict] = []
    counts: dict[str, int] = defaultdict(int)
    for (query_id, map_seed, checkpoint), policies in sorted(source_index.items()):
        for right in ("random", "degree"):
            left_row = policies.get("read")
            right_row = policies.get(right)
            if left_row is None or right_row is None:
                continue
            pair = f"read_minus_{right}"
            for metric in METRICS:
                left_value = left_row.get(metric)
                right_value = right_row.get(metric)
                if left_value is None or right_value is None:
                    continue
                contrast_rows.append({
                    "row_type": "heldout_paired_contrast",
                    "review_action": "REV-08",
                    "role": "heldout",
                    "query_id": query_id,
                    "map_seed": map_seed,
                    "traffic_seed": int(left_row["traffic_seed"]),
                    "checkpoint": checkpoint,
                    "left": "read",
                    "right": right,
                    "contrast": pair,
                    "metric": metric,
                    "left_value": float(left_value),
                    "right_value": float(right_value),
                    "delta": float(left_value) - float(right_value),
                })
                counts[f"{pair}|{checkpoint}|{metric}"] += 1
    if not contrast_rows:
        raise ValueError("no held-out paired contrasts could be formed")
    pq.write_table(pa.Table.from_pylist(contrast_rows), output / "metrics.parquet", compression="zstd")
    shutil.copyfile(parent / "selection.parquet", output / "selection.parquet")
    parent_summary = _json(parent / "summary.json")
    parent_manifest = _json(parent / "reviewer_manifest.json")
    summary = {
        "review_action": "REV-08",
        "compute_status": "COMPUTE_DONE",
        "outcome": "analysis_complete",
        "analysis_only": True,
        "performance_claim": False,
        "parent_run": str(parent),
        "parent_summary_sha256": file_digest(parent / "summary.json"),
        "heldout_query_rows": parent_summary["split"]["heldout_disjoint_count"],
        "seen_query_rows": parent_summary["split"]["schedule_count"],
        "checkpoints": list(CHECKPOINTS),
        "contrast_pairs": ["read_minus_random", "read_minus_degree"],
        "metric_names": list(METRICS),
        "contrast_rows": len(contrast_rows),
        "coverage": dict(sorted(counts.items())),
        "missing_parent_cells": parent_summary.get("missing_cells", []),
        "elapsed_seconds": time.monotonic() - started,
    }
    write_json(output / "summary.json", summary)
    write_json(output / "timing.json", {"elapsed_seconds": summary["elapsed_seconds"], "rows": len(contrast_rows),
                                         "parent": str(parent), "checkpoints": list(CHECKPOINTS)})
    write_json(output / "config.lock.json", {
        "review_action": "REV-08",
        "analysis_only": True,
        "parent_review_action": "REV-04.E5",
        "checkpoints": list(CHECKPOINTS),
        "paired_unit": "heldout_query_id_within_map_seed",
        "pairs": ["read_minus_random", "read_minus_degree"],
        "metrics": list(METRICS),
        "performance_claim": False,
    })
    write_json(output / "reference_inputs.json", {
        "review_action": "REV-08",
        "parent_run": str(parent),
        "parent_summary_sha256": file_digest(parent / "summary.json"),
        "parent_metrics_sha256": file_digest(parent / "metrics.parquet"),
        "parent_manifest": parent_manifest,
        "heldout_split": parent_summary["split"],
        "target_reference": parent_summary["target_reference"],
    })
    write_json(output / "reviewer_manifest.json", {
        "review_action": "REV-08",
        "analysis_only": True,
        "parent_review_action": "REV-04.E5",
        "metric_schema": {"contrast": "read metric minus comparison metric", "unit": "heldout query group paired within map seed"},
        "checkpoints": list(CHECKPOINTS),
        "pairs": ["read_minus_random", "read_minus_degree"],
        "coverage": dict(sorted(counts.items())),
        "missing_parent_cells": parent_summary.get("missing_cells", []),
    })
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.parent, args.output), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
