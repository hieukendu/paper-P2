"""Publish a prepared BEIR release only after full ingestion and ID checks."""

import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import tempfile

import pyarrow as pa
import pyarrow.parquet as pq

from ..io import digest, file_digest, file_lock, read_json, write_json
from .download import dataset_spec, download_dataset, extract_beir, verify_source_file
from .splits import build_static_splits, group_queries
from .store import DocumentStore, build_document_store


def iter_source_documents(path):
    with Path(path).open() as f:
        for line in f:
            record = json.loads(line)
            if not isinstance(record.get("_id"), str) or not isinstance(record.get("text"), str):
                raise ValueError("Invalid BEIR document schema")
            yield record["_id"], record.get("title", ""), record["text"]


def validate_prepared(path, expected=None):
    path = Path(path)
    manifest = read_json(path / "manifest.json")
    if manifest.get("status") != "VALIDATED":
        raise ValueError("Prepared release is not validated")
    for name, record in manifest["files"].items():
        file = path / name
        if file.stat().st_size != record["bytes"] or file_digest(file) != record["sha256"]:
            raise ValueError(f"Prepared artifact differs: {name}")
    if expected:
        for field in ("documents", "test_queries", "test_qrels"):
            if field in expected and manifest["counts"].get(field) != expected[field]:
                raise ValueError(f"Source count mismatch for {field}")
    return manifest


def prepare_dataset(name, cfg, root):
    spec = dataset_spec(name, root)
    if spec["parser"] in {"msmarco_documents", "orcas"}:
        from .scale import prepare_scale_dataset
        return prepare_scale_dataset(name, cfg, root)
    output = Path(cfg["paths"]["data"]) / "processed" / name
    with file_lock(output.parent / f".{name}.prepare.lock"):
        if (output / "manifest.json").exists():
            return validate_prepared(output, spec)
        if spec["parser"] != "beir":
            raise NotImplementedError(f"{spec['parser']} requires its dedicated scale/recovery adapter")
        files = download_dataset(spec, cfg["paths"])
        raw = files[0].parent
        extract_beir(files[0], raw / "extracted")
        source = raw / "extracted" / name
        if not all((source / name).exists() for name in ("corpus.jsonl", "queries.jsonl", "qrels/test.tsv")):
            raise ValueError("BEIR release is missing required source files")
        output.parent.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix=f".{name}-", dir=output.parent))
        store, counts = build_document_store(iter_source_documents(source / "corpus.jsonl"), stage)
        with (source / "queries.jsonl").open() as f:
            queries = [json.loads(line) for line in f]
        if any(not isinstance(q.get("_id"), str) or not isinstance(q.get("text"), str) for q in queries):
            raise ValueError("Invalid query schema")
        groups = group_queries((q["_id"], q["text"]) for q in queries)
        query_ids = {q["_id"] for q in queries}
        query_to_group = {qid: gid for gid, group in groups.items() for qid in group["query_ids"]}
        pq.write_table(pa.Table.from_pylist(list(groups.values())), stage / "queries.parquet")
        split_qids, records = {}, []
        duplicate_qrels = 0
        with sqlite3.connect(stage / "lookup.sqlite") as db:
            db.execute("create table qrels(split text, qid text, did text, grade integer, primary key(split,qid,did))")
            for file in sorted((source / "qrels").glob("*.tsv")):
                split_qids[file.stem] = set()
                with file.open() as f:
                    reader = csv.DictReader(f, delimiter="\t")
                    if reader.fieldnames != ["query-id", "corpus-id", "score"]:
                        raise ValueError("Unexpected BEIR qrels schema")
                    for record in reader:
                        qid, did, grade = record["query-id"], record["corpus-id"], int(record["score"])
                        if qid not in query_ids:
                            raise ValueError("Qrel query is missing")
                        found = db.execute("select row_id from documents where doc_id=?", (did,)).fetchone()
                        if found is None:
                            raise ValueError("Qrel document is missing")
                        previous = db.execute("select grade from qrels where split=? and qid=? and did=?",
                                              (file.stem, qid, did)).fetchone()
                        if previous is not None:
                            if previous[0] != grade:
                                raise ValueError("Conflicting qrel grade")
                            duplicate_qrels += 1
                            continue
                        db.execute("insert into qrels values(?,?,?,?)", (file.stem, qid, did, grade))
                        records.append({"split": file.stem, "query_id": qid,
                                        "group_id": query_to_group[qid], "doc_id": did,
                                        "doc_row": found[0], "grade": grade})
                        split_qids[file.stem].add(qid)
        pq.write_table(pa.Table.from_pylist(records), stage / "qrels.parquet")
        splits = build_static_splits(groups, split_qids, cfg["splits"]["master_seed"])
        write_json(stage / "splits/query_roles.json", splits)
        counts.update(raw_queries=len(queries), query_ids=len(query_ids), query_groups=len(groups),
                      test_queries=len(split_qids["test"]),
                      test_qrels=sum(r["split"] == "test" for r in records),
                      duplicate_qrels=duplicate_qrels,
                      split_queries={key: len(value) for key, value in split_qids.items()},
                      role_groups={key: len(value) for key, value in splits["roles"].items()})
        for field in ("documents", "test_queries", "test_qrels"):
            if field in spec and counts[field] != spec[field]:
                raise ValueError(f"{name}: {field} expected {spec[field]}, observed {counts[field]}; files preserved")
        artifacts = {}
        for file in sorted(stage.rglob("*")):
            if file.is_file():
                artifacts[str(file.relative_to(stage))] = {"bytes": file.stat().st_size, "sha256": file_digest(file)}
        manifest = {"dataset_id": name, "status": "VALIDATED", "parser_version": "beir-v1",
                    "downloaded_at": datetime.now(timezone.utc).isoformat(),
                    "source": {"url": spec["url"], "registry": spec["source"],
                               "license": spec["license"], **verify_source_file(
                                   files[0], ("md5", spec["md5"]) if "md5" in spec else None)},
                    "counts": counts, "files": artifacts, "split_hash": splits["hash"],
                    "text_policy": "title-newline-body-v1", "row_policy": "source-ingestion-order"}
        manifest["release_hash"] = digest(manifest)
        write_json(stage / "manifest.json", manifest)
        if output.exists():
            raise ValueError("Unfinished processed output exists; refusing overwrite")
        stage.rename(output)
        return validate_prepared(output, spec)


def open_validated_data(name, cfg):
    path = Path(cfg["paths"]["data"]) / "processed" / name
    validate_prepared(path)
    return DocumentStore(path)
