"""Search a restored index snapshot at depth 20 for REV-04."""

from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path

import numpy as np

from .index import ExactIndex
from .io import file_digest, write_json
from .calibration import Calibration


def load_query_vectors(jsonl: Path, vectors: Path):
    ids = [json.loads(line)["id"] for line in jsonl.open(encoding="utf-8")]
    return ids, np.load(vectors, mmap_mode="r")


def run(root: Path, index_vectors: Path, fidelity: Path, ids: Path, query_jsonl: Path,
        query_vectors: Path, output: Path, label: str, index_meta: Path | None = None):
    doc_ids = ids.read_text().splitlines()
    if index_meta is None:
        index_meta = index_vectors.parent / "index.json"
    calibration = Calibration()
    if index_meta.exists():
        metadata = json.loads(index_meta.read_text(encoding="utf-8"))
        calibration = Calibration(**{
            key: metadata.get("calibration", {}).get(key, value)
            for key, value in (("a", 1.0), ("b", 0.0), ("radius", None), ("reason", "identity"))
        })
    index = ExactIndex(np.load(index_vectors, mmap_mode="r"), doc_ids,
                       np.load(fidelity, mmap_mode="r"), calibration=calibration, chunk_rows=16384)
    query_ids, queries = load_query_vectors(query_jsonl, query_vectors)
    groups = json.loads((root / "data/processed/fiqa/splits/query_roles.json").read_text())["roles"]["eval"]
    eval_ids = sorted(groups)
    lookup = {qid: i for i, qid in enumerate(query_ids)}
    result = index.search(np.stack([queries[lookup[qid]] for qid in eval_ids]), k=20)
    output.mkdir(parents=True, exist_ok=True)
    with gzip.open(output / "retrieval.trec.gz", "wt", encoding="utf-8") as handle:
        for qid, rows in zip(eval_ids, result.rows):
            for rank, row in enumerate(rows[:20], 1):
                handle.write(f"{qid} Q0 {doc_ids[int(row)]} {rank} {-rank} {label}\n")
    write_json(output / "reference_inputs.json", {"index_vectors": {"path": str(index_vectors), "sha256": file_digest(index_vectors)},
        "index_fidelity": {"path": str(fidelity), "sha256": file_digest(fidelity)},
        "index_metadata": {"path": str(index_meta), "sha256": file_digest(index_meta)} if index_meta.exists() else None,
        "calibration": {"a": calibration.a, "b": calibration.b, "radius": calibration.radius,
                        "reason": calibration.reason},
        "query_vectors": {"path": str(query_vectors), "sha256": file_digest(query_vectors)},
        "depth": 20, "query_ids": eval_ids})
    write_json(output / "reviewer_manifest.json", {"review_action": "REV-04", "depth": 20,
        "search_replayed": True, "top10_prefix_preserved_check": "required", "performance_claim": False})
    write_json(output / "summary.json", {"compute_status": "COMPUTE_DONE", "outcome": "depth20_search_complete",
        "review_action": "REV-04", "analysis_only": True, "depth": 20, "evaluation_queries": len(eval_ids),
        "parent_label": label, "hardware_scope": "NVIDIA H100 80GB HBM3 MIG 2g.20gb", "performance_claim": False})
    write_json(output / "config.lock.json", {"reviewer_analysis": {"review_action": "REV-04", "depth": 20,
        "label": label, "analysis_only": True}})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--index-vectors", type=Path, required=True)
    parser.add_argument("--fidelity", type=Path, required=True)
    parser.add_argument("--ids", type=Path, required=True)
    parser.add_argument("--query-jsonl", type=Path, required=True)
    parser.add_argument("--query-vectors", type=Path, required=True)
    parser.add_argument("--index-meta", type=Path, default=None)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--label", required=True)
    args = parser.parse_args()
    run(args.root, args.index_vectors, args.fidelity, args.ids, args.query_jsonl,
        args.query_vectors, args.output, args.label, args.index_meta)
    print(json.dumps(json.loads((args.output / "summary.json").read_text()), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
