"""Aggregate reviewer FiQA cells with paired bootstrap/Holm inference.

The raw reviewer runners intentionally keep one immutable bundle per cell.  This
analysis-only entry point joins those bundles by query ID, computes descriptive
seed summaries, and performs the preregistered 10,000-draw paired bootstrap.
It never changes a raw run or makes a positive performance claim.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import time
import zlib

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from .config import load_config, redacted_config
from .io import file_digest, write_json


BOOTSTRAP_DRAWS = 10_000
REV01_METRICS = ("ndcg_at_10", "hit_at_10", "overlap_at_10")
MIGRATION_METRICS = (
    "ndcg_at_10",
    "hit_at_10",
    "nfr_at_1",
    "overlap_at_10",
    "f_accessed",
    "f_scheduled",
)


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _require_verified(path: Path) -> None:
    receipt = path / "sync.json"
    if not receipt.exists() or _json(receipt).get("status") != "VERIFIED":
        raise ValueError(f"raw reviewer bundle is not remotely verified: {path}")


def _run_rows(path: Path, family: str) -> tuple[list[dict], dict]:
    _require_verified(path)
    summary = _json(path / "summary.json")
    manifest = _json(path / "reviewer_manifest.json")
    table = pq.read_table(path / "metrics.parquet")
    rows = []
    for row in table.to_pylist():
        row = dict(row)
        row.update(
            {
                "family": family,
                "run_name": path.name,
                "map_seed": int(summary.get("map_seed", manifest.get("map_seed", -1))),
                "traffic_seed": int(summary.get("traffic_seed", manifest.get("traffic_seed", -1))),
                "variant": str(summary.get("variant") or "seed_bundle"),
            }
        )
        rows.append(row)
    return rows, {"summary": summary, "manifest": manifest, "path": str(path)}


def _paired_bootstrap(values: list[float], seed_key: str) -> dict:
    values = np.asarray(values, dtype=np.float64)
    if values.ndim != 1 or not len(values) or not np.isfinite(values).all():
        raise ValueError("paired differences must be finite and non-empty")
    seed = zlib.crc32(seed_key.encode("utf-8")) & 0xFFFFFFFF
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, len(values), size=(BOOTSTRAP_DRAWS, len(values)), dtype=np.int32)
    bootstrap = values[indices].mean(axis=1)
    signs = rng.choice(np.array([-1.0, 1.0]), size=(BOOTSTRAP_DRAWS, len(values)))
    signed = (values[None, :] * signs).mean(axis=1)
    observed = float(values.mean())
    return {
        "effect": observed,
        "ci95": [float(x) for x in np.quantile(bootstrap, [0.025, 0.975])],
        "p_raw": float((1 + np.count_nonzero(np.abs(signed) >= abs(observed))) / (BOOTSTRAP_DRAWS + 1)),
        "queries": int(len(values)),
        "draws": BOOTSTRAP_DRAWS,
        "unit": "query_group_conditional_on_seed_grid",
        "null_assumption": "method labels exchangeable within query groups",
    }


def _holm(rows: list[dict]) -> None:
    grouped: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for row in rows:
        grouped[(row["family"], row["checkpoint"], row["metric"])].append(row)
    for group in grouped.values():
        order = sorted(range(len(group)), key=lambda i: group[i]["p_raw"])
        running = 0.0
        for rank, index in enumerate(order):
            running = max(running, (len(group) - rank) * group[index]["p_raw"])
            group[index]["p_holm"] = float(min(1.0, running))


def _descriptive(rows: list[dict], metrics: tuple[str, ...]) -> list[dict]:
    buckets: dict[tuple, list[float]] = defaultdict(list)
    for row in rows:
        for metric in metrics:
            value = row.get(metric)
            if value is None:
                continue
            buckets[(row["family"], row["variant"], row["checkpoint"], metric)].append(float(value))
    result = []
    for (family, variant, checkpoint, metric), values in sorted(buckets.items()):
        arr = np.asarray(values, dtype=np.float64)
        result.append(
            {
                "row_type": "descriptive",
                "family": family,
                "variant": variant,
                "checkpoint": checkpoint,
                "metric": metric,
                "mean": float(arr.mean()),
                "std": float(arr.std(ddof=1)) if len(arr) > 1 else 0.0,
                "count": int(len(arr)),
            }
        )
    return result


def _analysis_rows(raw: list[dict]) -> tuple[list[dict], list[dict]]:
    descriptive: list[dict] = []
    contrasts: list[dict] = []

    rev01 = [row for row in raw if row["family"] == "REV-01"]
    descriptive.extend(_descriptive(rev01, REV01_METRICS))
    for method in ("op", "la", "residual_mlp"):
        left, right = f"query_side_{method}", f"forward_global_{method}"
        for metric in REV01_METRICS:
            values: dict[tuple[str, str], dict[str, float]] = defaultdict(dict)
            for row in rev01:
                if row.get("checkpoint") in {left, right}:
                    values[(str(row["query_id"]), str(row["map_seed"]))][row["checkpoint"]] = float(row[metric])
            diffs = defaultdict(list)
            for (qid, _seed), pair in values.items():
                if left in pair and right in pair:
                    diffs[qid].append(pair[left] - pair[right])
            per_query = [float(np.mean(v)) for _, v in sorted(diffs.items()) if v]
            if per_query:
                result = _paired_bootstrap(per_query, f"REV-01|{metric}|{method}")
                result.update({"row_type": "contrast", "family": "REV-01", "checkpoint": "aggregate",
                               "metric": metric, "left": left, "right": right,
                               "contrast": f"{left} - {right}", "p_holm": None})
                contrasts.append(result)

    for family, baseline, metrics in (
        ("REV-02", "G_R_C", MIGRATION_METRICS),
        ("REV-03", "rho1_safe", MIGRATION_METRICS),
    ):
        family_rows = [row for row in raw if row["family"] == family and row.get("ranking_role") == "snapshot"]
        variants = sorted({row["variant"] for row in family_rows})
        descriptive.extend(_descriptive(family_rows, metrics))
        checkpoints = sorted({row["checkpoint"] for row in family_rows})
        for checkpoint in checkpoints:
            for variant in variants:
                if variant == baseline:
                    continue
                for metric in metrics:
                    result = _contrast(family, family_rows, variant, baseline, checkpoint, metric)
                    if result is not None:
                        contrasts.append(result)
    _holm(contrasts)
    return descriptive, contrasts


def _contrast(family: str, rows: list[dict], left: str, right: str,
              checkpoint: str, metric: str) -> dict | None:
    values: dict[tuple[str, str], dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        if row.get("checkpoint") != checkpoint or row.get("variant") not in {left, right}:
            continue
        value = row.get(metric)
        if value is None:
            continue
        values[(str(row["query_id"]), str(row["map_seed"]))][row["variant"]].append(float(value))
    per_query: dict[str, list[float]] = defaultdict(list)
    for (query_id, _seed), pair in values.items():
        if left in pair and right in pair:
            per_query[query_id].append(float(np.mean(pair[left]) - np.mean(pair[right])))
    differences = [float(np.mean(v)) for _, v in sorted(per_query.items()) if v]
    if not differences:
        return None
    result = _paired_bootstrap(differences, f"{family}|{checkpoint}|{metric}|{left}|{right}")
    result.update({"row_type": "contrast", "family": family, "checkpoint": checkpoint,
                   "metric": metric, "left": left, "right": right,
                   "contrast": f"{left} - {right}", "p_holm": None})
    return result


def _diagnostics(metadata: list[dict]) -> list[dict]:
    result = []
    for item in metadata:
        summary, manifest = item["summary"], item["manifest"]
        timing_path = Path(item["path"]) / "timing.json"
        timing = _json(timing_path) if timing_path.exists() else {}
        result.append({
            "run_name": Path(item["path"]).name,
            "family": summary.get("review_action"),
            "map_seed": summary.get("map_seed"),
            "traffic_seed": summary.get("traffic_seed"),
            "variant": summary.get("variant"),
            "documents": summary.get("documents"),
            "evaluation_queries": summary.get("evaluation_queries"),
            "unique_paid_documents": summary.get("unique_paid_documents"),
            "f_accessed": summary.get("f_accessed"),
            "elapsed_seconds": summary.get("elapsed_seconds"),
            "accessor": timing.get("accessor", {}),
            "manifest_reviewer": manifest.get("reviewer", {}),
        })
    return result


def run(root: Path, output: Path) -> dict:
    started = time.time()
    raw, metadata = [], []
    patterns = (("REV-01", "REV-01-fiqa-query-controls-m*-t*"),
                ("REV-02", "REV-02-fiqa-*-m*-t*"),
                ("REV-03", "REV-03-fiqa-*-m*-t*"))
    for family, pattern in patterns:
        for path in sorted((root / "runs").glob(pattern)):
            # REV-04 post-hoc rankmetric bundles share the REV-01 parent
            # prefix but are derived analyses, not raw REV-01 metric cells.
            if path.name.endswith("-rankmetrics"):
                continue
            if not (path / "metrics.parquet").exists() or not (path / "summary.json").exists():
                continue
            rows, info = _run_rows(path, family)
            raw.extend(rows)
            metadata.append(info)
    if not raw:
        raise ValueError("no verified reviewer metrics found")
    descriptive, contrasts = _analysis_rows(raw)
    output.mkdir(parents=True, exist_ok=True)
    table_rows = descriptive + contrasts
    pq.write_table(pa.Table.from_pylist(table_rows), output / "metrics.parquet", compression="zstd")
    aggregate = {
        "review_action": "REV-AGGREGATE",
        "analysis_only": True,
        "bootstrap_draws": BOOTSTRAP_DRAWS,
        "families": {family: sum(1 for item in metadata if item["summary"].get("review_action") == family)
                     for family in ("REV-01", "REV-02", "REV-03")},
        "raw_rows": len(raw),
        "descriptive_rows": len(descriptive),
        "contrast_rows": len(contrasts),
        "missing_required_evidence": {
            "REV-01": [],
            "REV-02": [],
            "REV-03": [],
        },
        "performance_claim": False,
        "diagnostics": _diagnostics(metadata),
    }
    write_json(output / "reviewer_aggregate.json", aggregate)
    write_json(output / "reviewer_manifest.json", {
        "review_action": "REV-AGGREGATE",
        "families": ["REV-01", "REV-02", "REV-03"],
        "raw_run_count": len(metadata),
        "raw_input_sha256": {
            Path(item["path"]).name: file_digest(Path(item["path"]) / "metrics.parquet")
            for item in metadata
        },
        "paired_bootstrap_draws": BOOTSTRAP_DRAWS,
        "holm_correction": True,
        "performance_claim": False,
    })
    write_json(output / "reference_inputs.json", {
        "review_action": "REV-AGGREGATE",
        "raw_runs": sorted(Path(item["path"]).name for item in metadata),
        "raw_run_count": len(metadata),
        "analysis_scope": "verified_local_bundles_only",
    })
    write_json(output / "config.lock.json", {
        "reviewer_analysis": {
            "review_action": "REV-AGGREGATE",
            "bootstrap_draws": BOOTSTRAP_DRAWS,
            "holm": True,
            "performance_claim": False,
        },
        "source_config": redacted_config(load_config("configs/base.yaml", root=root)),
    })
    write_json(output / "timing.json", {
        "analysis_seconds": time.time() - started,
        "raw_rows": len(raw),
        "contrast_rows": len(contrasts),
        "mode": "paired_bootstrap_holm",
    })
    write_json(output / "summary.json", {
        "compute_status": "COMPUTE_DONE",
        "outcome": "analysis_complete",
        "review_action": "REV-AGGREGATE",
        "analysis_only": True,
        "raw_run_count": len(metadata),
        "raw_rows": len(raw),
        "contrast_rows": len(contrasts),
        "bootstrap_draws": BOOTSTRAP_DRAWS,
        "performance_claim": False,
        "hardware_scope": "NVIDIA H100 80GB HBM3 MIG 2g.20gb (analysis-only CPU)",
    })
    return aggregate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.root, args.output)
    print(json.dumps({key: result[key] for key in ("families", "raw_rows", "contrast_rows")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
