"""Post-hoc rank metrics for reviewer REV-04.

This module deliberately has no project-runtime dependencies beyond PyArrow.  The
accepted run bundles contain TREC rankings, so Overlap@k and extrapolated RBO can
be computed without re-encoding documents or changing the frozen experiment.
It is also usable with the system Python used for the analysis-only job.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path
import statistics
import time

import pyarrow as pa
import pyarrow.parquet as pq


DEFAULT_P = 0.9
DEFAULT_DEPTH = 10
OVERLAP_KS = (1, 3, 10, 20)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read_trec(path: Path) -> dict[str, dict[str, list[str]]]:
    """Read ``qid Q0 doc rank score run`` lines grouped by run and query."""

    grouped: dict[str, dict[str, list[tuple[int, str]]]] = defaultdict(lambda: defaultdict(list))
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            fields = line.split()
            if len(fields) < 6:
                raise ValueError(f"{path}:{line_number}: expected six TREC fields")
            qid, _, doc_id, rank_text, _, run_label = fields[:6]
            try:
                rank = int(rank_text)
            except ValueError as exc:
                raise ValueError(f"{path}:{line_number}: invalid rank {rank_text!r}") from exc
            grouped[run_label][qid].append((rank, doc_id))

    # Sort by the recorded rank and reject duplicate ranks/doc IDs.  The
    # accepted artifacts are deterministic; failing loudly protects against
    # silently changing the metric definition when a malformed ranking appears.
    result: dict[str, dict[str, list[str]]] = {}
    for label, queries in grouped.items():
        result[label] = {}
        for qid, rows in queries.items():
            rows.sort(key=lambda row: row[0])
            ranks = [rank for rank, _ in rows]
            docs = [doc_id for _, doc_id in rows]
            if len(ranks) != len(set(ranks)):
                raise ValueError(f"{path}: duplicate ranks for run={label} qid={qid}")
            if len(docs) != len(set(docs)):
                raise ValueError(f"{path}: duplicate docs for run={label} qid={qid}")
            result[label][qid] = docs
    return result


def overlap_at_k(current: list[str], target: list[str], k: int) -> float | None:
    if len(current) < k or len(target) < k:
        return None
    return len(set(current[:k]).intersection(target[:k])) / float(k)


def rbo_extrapolated(current: list[str], target: list[str], depth: int, p: float) -> float | None:
    """Return extrapolated RBO for equal-depth prefixes.

    ``A_d`` is prefix overlap at depth ``d``.  The tail term uses ``A_depth``
    exactly as specified in the reviewer plan; no unavailable rank positions are
    padded or inferred.
    """

    if len(current) < depth or len(target) < depth:
        return None
    current_seen: set[str] = set()
    target_seen: set[str] = set()
    weighted = 0.0
    last_overlap = 0.0
    for d in range(1, depth + 1):
        current_seen.add(current[d - 1])
        target_seen.add(target[d - 1])
        last_overlap = len(current_seen.intersection(target_seen)) / float(d)
        weighted += (p ** (d - 1)) * last_overlap
    return (1.0 - p) * weighted + (p**depth) * last_overlap


def _pair_labels(grouped: dict[str, dict[str, list[str]]]) -> list[tuple[str, str]]:
    labels = set(grouped)
    if "full_new_reference" in labels:
        return [(label, "full_new_reference") for label in sorted(labels) if label != "full_new_reference"]

    pairs: list[tuple[str, str]] = []
    for label in sorted(labels):
        if label.endswith("-current"):
            reference = label[: -len("-current")] + "-full-new"
            if reference in labels:
                pairs.append((label, reference))
    return pairs


def _mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def _std(values: list[float]) -> float | None:
    return statistics.stdev(values) if len(values) > 1 else (0.0 if values else None)


def analyze(input_path: Path, output_dir: Path, parent_name: str, p: float = DEFAULT_P) -> dict:
    started = time.time()
    grouped = read_trec(input_path)
    pairs = _pair_labels(grouped)
    if not pairs:
        raise ValueError(f"{input_path}: no current/reference ranking pairs found")

    rows: list[dict] = []
    aggregate: dict[str, dict[str, dict[str, float | int | None]]] = {}
    insufficient = 0
    depth20_available = 0
    for current_label, reference_label in pairs:
        current_queries = grouped[current_label]
        reference_queries = grouped[reference_label]
        common = sorted(set(current_queries).intersection(reference_queries))
        if not common:
            raise ValueError(f"{input_path}: no common queries for {current_label} vs {reference_label}")
        key = f"{current_label}__vs__{reference_label}"
        bucket: dict[str, list[float]] = defaultdict(list)
        for qid in common:
            current = current_queries[qid]
            reference = reference_queries[qid]
            values: dict[str, float | None] = {
                f"overlap_at_{k}": overlap_at_k(current, reference, k) for k in OVERLAP_KS
            }
            values["rbo_ext_10"] = rbo_extrapolated(current, reference, 10, p)
            values["rbo_ext_20"] = rbo_extrapolated(current, reference, 20, p)
            status = "OK"
            if values["rbo_ext_10"] is None:
                status = "INSUFFICIENT_DEPTH"
                insufficient += 1
            if values["rbo_ext_20"] is not None:
                depth20_available += 1
            row = {
                "parent": parent_name,
                "query_id": qid,
                "run_label": current_label,
                "reference_label": reference_label,
                "current_depth": len(current),
                "reference_depth": len(reference),
                "status": status,
                "rbo_p": p,
                **values,
            }
            rows.append(row)
            for name, value in values.items():
                if value is not None:
                    bucket[name].append(value)
        aggregate[key] = {
            "run_label": current_label,
            "reference_label": reference_label,
            "query_count": len(common),
            "current_depth_min": min(len(current_queries[q]) for q in common),
            "reference_depth_min": min(len(reference_queries[q]) for q in common),
            "metrics": {
                name: {"mean": _mean(bucket.get(name, [])), "std": _std(bucket.get(name, [])),
                       "count": len(bucket.get(name, []))}
                for name in ("overlap_at_1", "overlap_at_3", "overlap_at_10", "overlap_at_20",
                             "rbo_ext_10", "rbo_ext_20")
            },
        }

    output_dir.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pylist(rows)
    pq.write_table(table, output_dir / "metrics.parquet", compression="zstd")
    (output_dir / "reviewer_aggregate.json").write_text(
        json.dumps({"p": p, "depths": list(OVERLAP_KS), "comparisons": aggregate}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "reviewer_manifest.json").write_text(
        json.dumps(
            {
                "review_action": "REV-04",
                "metric_schema": {
                    "overlap": "|top_k(current) intersection top_k(reference)| / k",
                    "rbo": "(1-p) sum(p^(d-1) A_d) + p^K A_K",
                    "p": p,
                    "depths": list(OVERLAP_KS),
                    "rbo_depths": [10, 20],
                },
                "input_sha256": _sha256(input_path),
                "input_path": str(input_path),
                "pair_count": len(pairs),
                "query_row_count": len(rows),
                "insufficient_depth_rows": insufficient,
                "depth20_available_rows": depth20_available,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (output_dir / "timing.json").write_text(
        json.dumps({"analysis_seconds": time.time() - started, "rows": len(rows), "mode": "posthoc"}, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "compute_status": "COMPUTE_DONE",
        "outcome": "analysis_complete",
        "review_action": "REV-04",
        "analysis_only": True,
        "parent_name": parent_name,
        "parent_input": str(input_path),
        "parent_sha256": _sha256(input_path),
        "p": p,
        "rbo_depths": [10, 20],
        "overlap_depths": list(OVERLAP_KS),
        "comparison_count": len(pairs),
        "query_row_count": len(rows),
        "insufficient_depth_rows": insufficient,
        "depth20_available_rows": depth20_available,
        "depth20_status": "OBSERVED" if depth20_available else "INSUFFICIENT_DEPTH",
        "hardware_scope": "NVIDIA H100 80GB HBM3 MIG 2g.20gb (analysis-only CPU parsing)",
        "performance_claim": False,
        "elapsed_seconds": time.time() - started,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, dest="input_path")
    parser.add_argument("--output", required=True, type=Path, dest="output_dir")
    parser.add_argument("--parent-name", required=True)
    parser.add_argument("--p", type=float, default=DEFAULT_P)
    parser.add_argument("--parent-config", type=Path, default=None)
    parser.add_argument("--parent-summary", type=Path, default=None)
    parser.add_argument("--parent-reference", type=Path, default=None)
    return parser


def main() -> int:
    args = _parser().parse_args()
    summary = analyze(args.input_path, args.output_dir, args.parent_name, args.p)
    # Preserve the accepted config as an immutable input reference while adding
    # a small derived-analysis section.  The parent config is optional to keep
    # the parser useful for standalone fixture tests.
    if args.parent_config and args.parent_config.exists():
        config = json.loads(args.parent_config.read_text(encoding="utf-8"))
    else:
        config = {"reviewer_analysis": {}}
    config = deepcopy(config)
    config.setdefault("reviewer_analysis", {}).update(
        {"review_action": "REV-04", "analysis_only": True, "rbo_p": args.p, "input": str(args.input_path)}
    )
    (args.output_dir / "config.lock.json").write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    parent_reference = {}
    if args.parent_reference and args.parent_reference.exists():
        parent_reference = json.loads(args.parent_reference.read_text(encoding="utf-8"))
    (args.output_dir / "reference_inputs.json").write_text(
        json.dumps(
            {
                "review_action": "REV-04",
                "analysis_only": True,
                "parent_name": args.parent_name,
                "parent_input_sha256": summary["parent_sha256"],
                "parent_reference": parent_reference,
                "metric_depths": {"overlap": list(OVERLAP_KS), "rbo": [10, 20]},
                "rbo_p": args.p,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
