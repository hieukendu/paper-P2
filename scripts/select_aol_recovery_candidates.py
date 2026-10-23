"""Build a deterministic, local-only AOL-IA recovery candidate source.

The reduced E6 release needs 50,000 recovered documents, not a complete
download of every URL in the 1.5M-row id2wb mapping.  This helper selects a
larger deterministic candidate set using the same document hash rule as the
preparer.  The full, checksummed id2wb mapping remains the authoritative
source; the candidate file is only a transport optimization for the local
recovery step and is never published.
"""

import argparse
import gzip
import hashlib
import heapq
import json
from pathlib import Path


DEFAULT_SEED = 20261020
DEFAULT_CAP = 75_000


def _key(seed, doc_id):
    return int(hashlib.sha256(
        f"{seed}\0AOL-uniform-document\0{doc_id}".encode()).hexdigest(), 16)


def select_candidates(source, output, cap=DEFAULT_CAP, seed=DEFAULT_SEED,
                      metadata_output=None):
    source = Path(source)
    output = Path(output)
    if output.exists():
        raise ValueError(f"refusing to overwrite existing candidate source: {output}")
    if cap < 50_000:
        raise ValueError("candidate cap must be at least the 50,000-document E6 cap")

    heap = []
    selected = {}
    seen = set()
    source_rows = 0
    invalid_rows = 0
    with gzip.open(source, "rt", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            fields = line.rstrip("\n").split("\t")
            if len(fields) != 3:
                raise ValueError(f"invalid id2wb row at line {line_number}")
            doc_id, url, wb_url = fields
            expected_id = hashlib.md5(url.encode()).hexdigest()[:12]
            if doc_id != expected_id:
                invalid_rows += 1
                continue
            if doc_id in seen:
                raise ValueError(f"duplicate document ID at line {line_number}: {doc_id}")
            seen.add(doc_id)
            source_rows += 1
            key = _key(seed, doc_id)
            item = (-key, doc_id)
            if len(heap) < cap:
                heapq.heappush(heap, item)
                selected[doc_id] = (key, url, wb_url)
            elif key < -heap[0][0]:
                _, evicted_id = heapq.heapreplace(heap, item)
                selected.pop(evicted_id)
                selected[doc_id] = (key, url, wb_url)

    if len(selected) != cap:
        raise ValueError(f"source has only {len(selected)} usable rows; need {cap}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(output, "wt", encoding="utf-8", newline="") as stream:
        for _, url, wb_url in sorted(selected.values(), key=lambda row: (row[0], row[1])):
            doc_id = hashlib.md5(url.encode()).hexdigest()[:12]
            stream.write(f"{doc_id}\t{url}\t{wb_url}\n")

    metadata = {
        "scope": "deterministic-candidate-subset-v1",
        "selection": "sha256(seed\\0AOL-uniform-document\\0doc_id)",
        "seed": seed,
        "candidate_documents": cap,
        "source_rows": source_rows,
        "invalid_source_rows": invalid_rows,
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "candidate_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "published": False,
    }
    metadata_json = json.dumps(metadata, indent=2, sort_keys=True) + "\n"
    output.with_suffix(output.suffix + ".json").write_text(metadata_json, encoding="utf-8")
    if metadata_output is not None:
        metadata_output = Path(metadata_output)
        metadata_output.parent.mkdir(parents=True, exist_ok=True)
        metadata_output.write_text(metadata_json, encoding="utf-8")
    return metadata


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cap", type=int, default=DEFAULT_CAP)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--metadata-output", type=Path, default=None)
    args = parser.parse_args()
    print(json.dumps(select_candidates(args.source, args.output, args.cap, args.seed,
                                       args.metadata_output), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
