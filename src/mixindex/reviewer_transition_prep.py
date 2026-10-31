"""Prepare transition-specific calibration query vectors from the frozen pools."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import numpy as np

from .io import file_digest, write_json


def _query_ids(path: Path) -> list[str]:
    ids = []
    for line in path.open(encoding="utf-8"):
        ids.append(str(json.loads(line)["id"]))
    return ids


def prepare(root: Path, pair: str, old_query_vectors: Path, output: Path) -> dict:
    root = Path(root)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    parent = root / "runs/REV-02-fiqa-g_r_c-m17-t101/checkpoints/accessed-000002020"
    pools_path = parent / "calibration_pools.json"
    pools = json.loads(pools_path.read_text())
    ids = _query_ids(root / "runs/reviewer_inputs/fiqa_text/queries.jsonl")
    vectors = np.load(old_query_vectors, mmap_mode="r")
    if vectors.shape[0] != len(ids):
        raise ValueError("transition query vectors are not row aligned")
    by_id = {qid: int(index) for index, qid in enumerate(ids)}
    selected = []
    selected_ids = []
    for role in ("cal_fit", "cal_check"):
        for qid, _ in pools[role]["pairs"]:
            qid = str(qid)
            if qid not in by_id:
                raise ValueError(f"calibration query missing from transition vectors: {qid}")
            selected_ids.append(qid)
            selected.append(np.asarray(vectors[by_id[qid]], dtype=np.float32))
    np.savez(output / "calibration_queries.npz", query_ids=np.asarray(selected_ids, dtype=str),
             vectors=np.stack(selected).astype(np.float32, copy=False))
    shutil.copyfile(pools_path, output / "calibration_pools.json")
    result = {
        "pair": pair,
        "source_query_vectors": str(old_query_vectors),
        "source_query_vectors_sha256": file_digest(old_query_vectors),
        "parent_calibration_pools": str(pools_path),
        "calibration_queries": len(selected_ids),
        "dimension": int(vectors.shape[1]),
        "calibration_queries_sha256": file_digest(output / "calibration_queries.npz"),
        "calibration_pools_sha256": file_digest(output / "calibration_pools.json"),
    }
    write_json(output / "transition_inputs.json", result)
    print(json.dumps(result, sort_keys=True))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--pair", required=True)
    parser.add_argument("--old-query-vectors", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.root, args.pair, args.old_query_vectors, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
