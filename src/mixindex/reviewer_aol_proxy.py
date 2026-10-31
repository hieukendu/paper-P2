"""Join the released redacted AOL signal with accepted E6 rankings (REV-09).

The public release contains group IDs, clicked document IDs and temporal weeks,
but no raw query/document text.  This analysis therefore computes a
click-derived operational proxy only.  It never labels clicks as unbiased
relevance and keeps the covered-population denominators explicit.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import statistics
import time

import pyarrow as pa
import pyarrow.parquet as pq


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def read_pool(path: Path) -> set[str]:
    return {line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}


def read_rankings(path: Path) -> dict[str, dict[str, list[str]]]:
    """Return label -> group -> ranked document IDs."""

    result: dict[str, dict[str, list[tuple[int, str]]]] = defaultdict(lambda: defaultdict(list))
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            fields = line.split()
            if len(fields) < 6:
                raise ValueError(f"{path}:{line_no}: malformed TREC line")
            group_id, _, doc_id, rank_text, _, label = fields[:6]
            result[label][group_id].append((int(rank_text), doc_id))
    return {
        label: {
            group: [doc for _, doc in sorted(rows)]
            for group, rows in groups.items()
        }
        for label, groups in result.items()
    }


def load_click_signal(events_path: Path, pool: set[str]):
    table = pq.read_table(events_path, columns=["week", "group_id", "doc_id", "clicked"])
    weeks = table["week"].to_pylist()
    groups = table["group_id"].to_pylist()
    docs = table["doc_id"].to_pylist()
    clicked = table["clicked"].to_pylist()
    clicks: dict[tuple[int, str], set[str]] = defaultdict(set)
    pool_clicks: dict[tuple[int, str], set[str]] = defaultdict(set)
    all_events: dict[int, int] = defaultdict(int)
    clicked_events: dict[int, int] = defaultdict(int)
    clicked_event_rows_in_pool: dict[int, int] = defaultdict(int)
    clicked_docs: dict[int, set[str]] = defaultdict(set)
    clicked_pool_docs: dict[int, set[str]] = defaultdict(set)
    for week, group, doc, is_clicked in zip(weeks, groups, docs, clicked):
        week_number = int(week) + 1  # release week-0 is E6 week-1
        all_events[week_number] += 1
        if not is_clicked or not doc or not group:
            continue
        clicked_events[week_number] += 1
        clicked_docs[week_number].add(doc)
        clicks[(week_number, group)].add(doc)
        if doc in pool:
            clicked_event_rows_in_pool[week_number] += 1
            clicked_pool_docs[week_number].add(doc)
            pool_clicks[(week_number, group)].add(doc)
    return (clicks, pool_clicks), {
        "selected_event_rows": sum(all_events.values()),
        "clicked_event_rows": sum(clicked_events.values()),
        "selected_event_rows_by_week": dict(sorted(all_events.items())),
        "clicked_event_rows_by_week": dict(sorted(clicked_events.items())),
        "clicked_event_rows_in_pool": sum(clicked_event_rows_in_pool.values()),
        "clicked_event_rows_in_pool_by_week": dict(sorted(clicked_event_rows_in_pool.items())),
        "clicked_docs": sum(len(v) for v in clicked_docs.values()),
        "clicked_docs_in_pool": sum(len(v) for v in clicked_pool_docs.values()),
        "clicked_docs_by_week": {str(k): len(v) for k, v in sorted(clicked_docs.items())},
        "clicked_docs_in_pool_by_week": {str(k): len(v) for k, v in sorted(clicked_pool_docs.items())},
    }


def _mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def _weighted(values: list[tuple[float, int]]) -> float | None:
    denominator = sum(weight for _, weight in values)
    return sum(value * weight for value, weight in values) / denominator if denominator else None


def analyse_policy(policy: str, rankings: dict[str, dict[str, list[str]]], click_sets, pool: set[str]) -> list[dict]:
    clicks, pool_clicks = click_sets
    rows: list[dict] = []
    for label, groups in sorted(rankings.items()):
        if not label.startswith("e6-week-"):
            continue
        parts = label.split("-")
        week = int(parts[2])
        if not (label.endswith("-current") or label.endswith("-full-new")):
            continue
        for group_id, top_docs in groups.items():
            clicked_docs = clicks.get((week, group_id), set())
            in_pool = pool_clicks.get((week, group_id), set())
            hit = bool(clicked_docs.intersection(top_docs[:10])) if clicked_docs else None
            pool_hit = bool(in_pool.intersection(top_docs[:10])) if in_pool else None
            recall = (len(clicked_docs.intersection(top_docs[:10])) / len(clicked_docs)) if clicked_docs else None
            pool_recall = (len(in_pool.intersection(top_docs[:10])) / len(in_pool)) if in_pool else None
            rows.append(
                {
                    "policy": policy,
                    "week": week,
                    "group_id": group_id,
                    "ranking_label": label,
                    "ranking_role": "target" if label.endswith("full-new") else "policy",
                    "ranking_depth": len(top_docs),
                    "clicked_doc_count": len(clicked_docs),
                    "clicked_doc_count_in_pool": len(in_pool),
                    "clicked_hit_at_10": hit,
                    "clicked_hit_at_10_pool": pool_hit,
                    "clicked_recall_at_10": recall,
                    "clicked_recall_at_10_pool": pool_recall,
                    "signal_available": bool(clicked_docs),
                    "pool_signal_available": bool(in_pool),
                }
            )
    return rows


def aggregate(rows: list[dict]) -> dict:
    result = {}
    for key in sorted({(r["policy"], r["ranking_role"]) for r in rows}):
        policy, role = key
        subset = [r for r in rows if (r["policy"], r["ranking_role"]) == key]
        weeks = {}
        for week in sorted({r["week"] for r in subset}):
            week_rows = [r for r in subset if r["week"] == week]
            weeks[str(week)] = _aggregate_subset(week_rows)
        result[f"{policy}__{role}"] = {
            "policy": policy,
            "ranking_role": role,
            "overall": _aggregate_subset(subset),
            "weeks": weeks,
        }
    return result


def _aggregate_subset(rows: list[dict]) -> dict:
    signal = [r for r in rows if r["signal_available"]]
    pool_signal = [r for r in rows if r["pool_signal_available"]]
    def vals(name, source):
        return [float(r[name]) for r in source if r[name] is not None]
    return {
        "groups": len(rows),
        "groups_with_clicks": len(signal),
        "groups_with_clicked_docs_in_pool": len(pool_signal),
        "clicked_hit_at_10_group_macro": _mean(vals("clicked_hit_at_10", signal)),
        "clicked_hit_at_10_pool_macro": _mean(vals("clicked_hit_at_10_pool", pool_signal)),
        "clicked_recall_at_10_group_macro": _mean(vals("clicked_recall_at_10", signal)),
        "clicked_recall_at_10_pool_macro": _mean(vals("clicked_recall_at_10_pool", pool_signal)),
        "clicked_hit_at_10_event_weighted": _weighted(
            [(float(r["clicked_hit_at_10"]), r["clicked_doc_count"]) for r in signal if r["clicked_hit_at_10"] is not None]
        ),
        "clicked_recall_at_10_event_weighted": _weighted(
            [(float(r["clicked_recall_at_10"]), r["clicked_doc_count"]) for r in signal if r["clicked_recall_at_10"] is not None]
        ),
        "clicked_recall_at_10_pool_event_weighted": _weighted(
            [(float(r["clicked_recall_at_10_pool"]), r["clicked_doc_count_in_pool"]) for r in pool_signal if r["clicked_recall_at_10_pool"] is not None]
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--pool", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ranking", action="append", nargs=2, metavar=("POLICY", "PATH"), required=True)
    parser.add_argument("--release-hash", required=True)
    args = parser.parse_args()
    started = time.time()
    pool = read_pool(args.pool)
    clicks, coverage = load_click_signal(args.events, pool)
    rows: list[dict] = []
    parent_refs = []
    for policy, raw_path in args.ranking:
        path = Path(raw_path)
        ranking = read_rankings(path)
        rows.extend(analyse_policy(policy, ranking, clicks, pool))
        parent_refs.append({"policy": policy, "path": str(path), "sha256": sha256(path)})
    if not rows:
        raise ValueError("No E6 ranking rows were found")
    args.output.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows), args.output / "metrics.parquet", compression="zstd")
    comparison = aggregate(rows)
    aggregate_doc = {
        "review_action": "REV-09",
        "proxy_status": "SIGNAL_JOINED",
        "denominators": {
            "group_macro": "one row per ranked group/week; click-bearing groups only for hit/recall",
            "event_weighted": "clicked event-row count per group; descriptive, not unbiased utility",
            "pool_recall": "clicked-document set intersected with the frozen 50k document pool",
        },
        "coverage": {**coverage, "frozen_pool_documents": len(pool)},
        "comparisons": comparison,
    }
    (args.output / "reviewer_aggregate.json").write_text(json.dumps(aggregate_doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest = {
        "review_action": "REV-09",
        "proxy_status": "SIGNAL_JOINED",
        "release_hash": args.release_hash,
        "events_sha256": sha256(args.events),
        "pool_sha256": sha256(args.pool),
        "policies": [policy for policy, _ in args.ranking],
        "rows": len(rows),
        "coverage": coverage,
        "claim_scope": "click-derived operational proxy on covered redacted AOL population",
        "performance_claim": False,
    }
    (args.output / "reviewer_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (args.output / "timing.json").write_text(json.dumps({"analysis_seconds": time.time() - started, "rows": len(rows), "mode": "posthoc_join"}, indent=2) + "\n", encoding="utf-8")
    summary = {
        "compute_status": "COMPUTE_DONE",
        "outcome": "proxy_join_complete",
        "review_action": "REV-09",
        "analysis_only": True,
        "proxy_status": "SIGNAL_JOINED",
        "policies": [policy for policy, _ in args.ranking],
        "rows": len(rows),
        "coverage": coverage,
        "frozen_pool_documents": len(pool),
        "release_hash": args.release_hash,
        "hardware_scope": "NVIDIA H100 80GB HBM3 MIG 2g.20gb (analysis-only CPU parsing)",
        "performance_claim": False,
        "parent_runs": parent_refs,
        "elapsed_seconds": time.time() - started,
    }
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (args.output / "reference_inputs.json").write_text(json.dumps({
        "review_action": "REV-09", "analysis_only": True, "release_hash": args.release_hash,
        "events": {"path": str(args.events), "sha256": sha256(args.events)},
        "pool": {"path": str(args.pool), "sha256": sha256(args.pool), "documents": len(pool)},
        "rankings": parent_refs,
        "coverage": coverage,
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
