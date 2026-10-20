"""Streaming MS MARCO document and ORCAS preparation.

The scale inputs are kept separate from BEIR preparation because MS MARCO's
judged development files and ORCAS' static query graph have different roles.
No model inference or quality labels are used while building these releases.
"""

from __future__ import annotations

from datetime import datetime, timezone
import gzip
from pathlib import Path
import sqlite3
import tempfile

import pyarrow as pa
import pyarrow.parquet as pq

from ..io import digest, file_digest, file_lock, read_json, write_json
from .download import dataset_spec, download_dataset
from .splits import group_queries, normalize_query, stable_key
from .store import build_document_store


def _artifact_manifest(stage):
    return {str(path.relative_to(stage)): {"bytes": path.stat().st_size,
            "sha256": file_digest(path)} for path in sorted(Path(stage).rglob("*")) if path.is_file()}


def _empty_qrels(path):
    schema = pa.schema([("split", pa.string()), ("query_id", pa.string()),
                        ("group_id", pa.string()), ("doc_id", pa.string()),
                        ("doc_row", pa.int64()), ("grade", pa.int64())])
    pq.write_table(pa.Table.from_pylist([], schema=schema), path)


def _write_rows(path, rows, schema, batch_size=100_000):
    writer = None
    try:
        for start in range(0, len(rows), batch_size):
            table = pa.Table.from_pylist(rows[start:start + batch_size], schema=schema)
            if writer is None:
                writer = pq.ParquetWriter(path, schema, compression="zstd")
            writer.write_table(table)
    finally:
        if writer is not None:
            writer.close()


def _prepare_msmarco(name, cfg, root, spec):
    output = Path(cfg["paths"]["data"]) / "processed" / name
    output.parent.mkdir(parents=True, exist_ok=True)
    raw_files = download_dataset(spec, cfg["paths"])
    raw_by_name = {Path(path).name: Path(path) for path in raw_files}
    try:
        docs_file = raw_by_name["msmarco-docs.tsv.gz"]
        queries_file = raw_by_name["msmarco-docdev-queries.tsv.gz"]
        qrels_file = raw_by_name["msmarco-docdev-qrels.tsv.gz"]
    except KeyError as exc:
        raise ValueError("MS MARCO download is missing a required file") from exc
    stage = Path(tempfile.mkdtemp(prefix=f".{name}-", dir=output.parent))
    try:
        def documents():
            with gzip.open(docs_file, "rt", encoding="utf-8", newline="") as stream:
                for line in stream:
                    fields = line.rstrip("\r\n").split("\t")
                    if len(fields) < 4:
                        raise ValueError("MS MARCO document row has fewer than four fields")
                    # A tab in the body is part of the body, not an extra column.
                    yield fields[0], fields[2], "\t".join(fields[3:])

        store, counts = build_document_store(documents(), stage)
        queries = []
        seen_queries = {}
        with gzip.open(queries_file, "rt", encoding="utf-8", newline="") as stream:
            for line in stream:
                fields = line.rstrip("\r\n").split("\t", 1)
                if len(fields) != 2 or not fields[0] or fields[0] in seen_queries:
                    if fields and fields[0] in seen_queries and seen_queries[fields[0]] == fields[1]:
                        continue
                    raise ValueError("Invalid or conflicting MS MARCO dev query")
                seen_queries[fields[0]] = fields[1]
                queries.append((fields[0], fields[1]))
        groups = group_queries(queries)
        pq.write_table(pa.Table.from_pylist(list(groups.values()), schema=pa.schema([
            ("group_id", pa.string()), ("normalized_text", pa.string()),
            ("text", pa.string()), ("representative_id", pa.string()),
            ("query_ids", pa.list_(pa.string()))])), stage / "queries.parquet",
                      compression="zstd")
        query_to_group = {qid: gid for gid, group in groups.items() for qid in group["query_ids"]}
        qrel_rows, qrel_seen = [], set()
        with sqlite3.connect(stage / "lookup.sqlite") as db, gzip.open(
                qrels_file, "rt", encoding="utf-8", newline="") as stream:
            for line in stream:
                fields = line.split()
                if len(fields) != 4 or fields[1] != "0":
                    raise ValueError("Unexpected MS MARCO qrels schema")
                qid, did, grade = fields[0], fields[2], int(fields[3])
                if qid not in query_to_group:
                    raise ValueError("MS MARCO qrel query is missing")
                key = (qid, did)
                if key in qrel_seen:
                    continue
                found = db.execute("select row_id from documents where doc_id=?", (did,)).fetchone()
                if found is None:
                    raise ValueError("MS MARCO qrel document is missing")
                qrel_seen.add(key)
                qrel_rows.append({"split": "dev", "query_id": qid,
                                  "group_id": query_to_group[qid], "doc_id": did,
                                  "doc_row": found[0], "grade": grade})
        pq.write_table(pa.Table.from_pylist(qrel_rows, schema=pa.schema([
            ("split", pa.string()), ("query_id", pa.string()), ("group_id", pa.string()),
            ("doc_id", pa.string()), ("doc_row", pa.int64()), ("grade", pa.int64())
        ])), stage / "qrels.parquet", compression="zstd")
        roles = {"eval": sorted(groups), "tune": [], "schedule": [],
                 "cal_fit": [], "cal_check": []}
        write_json(stage / "splits/query_roles.json", {
            "seed": cfg["splits"]["master_seed"], "roles": roles,
            "query_policy": "MS-MARCO-judged-dev-heldout-v1", "hash": digest(roles),
            "calibration_available": False})
        counts.update(raw_queries=len(queries), query_ids=len(seen_queries),
                      query_groups=len(groups), test_queries=len(groups),
                      test_qrels=len(qrel_rows), judged_dev_queries=len(groups),
                      judged_dev_qrels=len(qrel_rows), duplicate_qrels=len(queries) - len(seen_queries),
                      split_queries={"dev": len(groups)}, role_groups={k: len(v) for k, v in roles.items()})
        if counts["documents"] != spec["documents"] or counts["test_queries"] != spec["test_queries"] \
                or counts["test_qrels"] != spec["test_qrels"]:
            raise ValueError(f"{name}: registry count mismatch: {counts}")
        manifest = {"dataset_id": name, "status": "VALIDATED", "parser_version": "msmarco-doc-v1",
                    "downloaded_at": datetime.now(timezone.utc).isoformat(),
                    "source": {"url": spec["base_url"], "registry": spec["source"],
                               "license": spec["license"],
                               "files": {p.name: {"bytes": p.stat().st_size, "sha256": file_digest(p)}
                                         for p in raw_files}},
                    "counts": counts, "files": _artifact_manifest(stage),
                    "split_hash": digest(roles),
                    "text_policy": "title-newline-body-v1", "row_policy": "source-ingestion-order",
                    "judged_split": "dev"}
        manifest["release_hash"] = digest(manifest)
        write_json(stage / "manifest.json", manifest)
        output.parent.mkdir(parents=True, exist_ok=True)
        if output.exists():
            raise ValueError("Unfinished processed MS MARCO output exists; refusing overwrite")
        stage.rename(output)
        return read_json(output / "manifest.json")
    except Exception:
        # Preserve the stage for inspection; no partially prepared release is published.
        raise


def _read_dev_normalized(ms_path):
    table = pq.read_table(Path(ms_path) / "queries.parquet", columns=["normalized_text"])
    return set(table.column("normalized_text").to_pylist())


def _write_orcas_query_rows(db, stage):
    schema = pa.schema([("group_id", pa.string()), ("normalized_text", pa.string()),
                        ("text", pa.string()), ("representative_id", pa.string()),
                        ("source_query_count", pa.int64()), ("excluded_dev", pa.bool_())])
    with (stage / "queries.parquet").open("wb") as output:
        writer = pq.ParquetWriter(output, schema, compression="zstd")
        cursor = db.execute("select group_id, normalized_text, text, representative_id, source_count, excluded_dev from groups order by group_id")
        while True:
            rows = [{"group_id": r[0], "normalized_text": r[1], "text": r[2],
                     "representative_id": r[3], "source_query_count": r[4],
                     "excluded_dev": bool(r[5])} for r in cursor.fetchmany(100_000)]
            if not rows:
                break
            writer.write_table(pa.Table.from_pylist(rows, schema=schema))
        writer.close()


def _write_orcas_source_queries(db, stage):
    schema = pa.schema([("query_id", pa.string()), ("group_id", pa.string())])
    with (stage / "source_queries.parquet").open("wb") as output:
        writer = pq.ParquetWriter(output, schema, compression="zstd")
        cursor = db.execute("select qid, group_id from source_queries order by qid")
        while True:
            rows = [{"query_id": r[0], "group_id": r[1]} for r in cursor.fetchmany(100_000)]
            if not rows:
                break
            writer.write_table(pa.Table.from_pylist(rows, schema=schema))
        writer.close()


def _write_orcas_edges(db, stage):
    schema = pa.schema([("group_id", pa.string()), ("doc_row", pa.int64())])
    with (stage / "traffic.parquet").open("wb") as output:
        writer = pq.ParquetWriter(output, schema, compression="zstd")
        cursor = db.execute("select group_id, doc_row from traffic_edges order by group_id, doc_row")
        while True:
            rows = [{"group_id": r[0], "doc_row": r[1]} for r in cursor.fetchmany(100_000)]
            if not rows:
                break
            writer.write_table(pa.Table.from_pylist(rows, schema=schema))
        writer.close()


def _prepare_orcas(name, cfg, root, spec):
    output = Path(cfg["paths"]["data"]) / "processed" / name
    output.parent.mkdir(parents=True, exist_ok=True)
    docs_path = Path(cfg["paths"]["data"]) / "processed" / "msmarco-docs-v1"
    docs_manifest = read_json(docs_path / "manifest.json")
    if docs_manifest.get("status") != "VALIDATED":
        raise ValueError("ORCAS requires the validated MS MARCO document release")
    raw_file = download_dataset(spec, cfg["paths"])[0]
    stage = Path(tempfile.mkdtemp(prefix=f".{name}-", dir=output.parent))
    db_path = stage / "orcas.sqlite"
    try:
        excluded_norm = _read_dev_normalized(docs_path)
        with sqlite3.connect(db_path) as db:
            db.execute("pragma journal_mode=wal")
            db.execute("create table source_queries(qid text primary key, text text not null, normalized_text text not null, group_id text not null, conflict integer not null default 0)")
            db.execute("create table raw_edges(qid text not null, did text not null, primary key(qid,did))")
            raw_records = 0
            empty_query_records = 0
            source_rows, edge_rows = [], []
            with gzip.open(raw_file, "rt", encoding="utf-8", newline="") as stream:
                for line in stream:
                    fields = line.rstrip("\r\n").split("\t")
                    # ORCAS contains legitimate records whose query text is
                    # empty (the source registry still counts these rows and
                    # query IDs). Preserve those records for auditability;
                    # qid and document ID remain required join keys.
                    if len(fields) != 4 or not fields[0] or not fields[2]:
                        raise ValueError("Invalid ORCAS row schema")
                    qid, query, did, _url = fields
                    empty_query_records += not bool(query)
                    normalized = normalize_query(query)
                    gid = __import__("hashlib").sha256(normalized.encode()).hexdigest()
                    source_rows.append((qid, query, normalized, gid))
                    edge_rows.append((qid, did))
                    raw_records += 1
                    if len(source_rows) >= 10_000:
                        db.executemany("insert into source_queries(qid,text,normalized_text,group_id) values(?,?,?,?) on conflict(qid) do update set conflict=1 where source_queries.text != excluded.text", source_rows)
                        db.executemany("insert or ignore into raw_edges(qid,did) values(?,?)", edge_rows)
                        source_rows.clear()
                        edge_rows.clear()
                if source_rows:
                    db.executemany("insert into source_queries(qid,text,normalized_text,group_id) values(?,?,?,?) on conflict(qid) do update set conflict=1 where source_queries.text != excluded.text", source_rows)
                    db.executemany("insert or ignore into raw_edges(qid,did) values(?,?)", edge_rows)
            db.commit()
            conflict = db.execute("select count(*) from source_queries where conflict=1").fetchone()[0]
            if conflict:
                raise ValueError(f"ORCAS has {conflict} conflicting source query IDs")
            db.execute("create table groups(group_id text primary key, normalized_text text not null, text text not null, representative_id text not null, source_count integer not null, excluded_dev integer not null default 0)")
            db.execute("insert into groups select group_id, min(normalized_text), (select s2.text from source_queries s2 where s2.group_id=s.group_id order by s2.qid limit 1), min(qid), count(*), 0 from source_queries s group by group_id")
            db.executemany("update groups set excluded_dev=1 where normalized_text=?", ((value,) for value in excluded_norm))
            excluded_group_count = db.execute("select count(*) from groups where excluded_dev=1").fetchone()[0]
            db.execute("attach database ? as docsdb", (str(docs_path / "lookup.sqlite"),))
            db.execute("create table traffic_edges(group_id text not null, doc_row integer not null, primary key(group_id,doc_row))")
            db.execute("insert or ignore into traffic_edges select s.group_id,d.row_id from raw_edges r join source_queries s on s.qid=r.qid join docsdb.documents d on d.doc_id=r.did join groups g on g.group_id=s.group_id where g.excluded_dev=0")
            db.commit()
            unique_edges = db.execute("select count(*) from traffic_edges").fetchone()[0]
            raw_edges = db.execute("select count(*) from raw_edges").fetchone()[0]
            missing_documents = db.execute("select count(*) from raw_edges r join source_queries s on s.qid=r.qid join groups g on g.group_id=s.group_id left join docsdb.documents d on d.doc_id=r.did where g.excluded_dev=0 and d.row_id is null").fetchone()[0]
            duplicate_edges = raw_records - raw_edges
            group_ids = [row[0] for row in db.execute("select group_id from groups where excluded_dev=0")]
            ordered = sorted(group_ids, key=lambda value: stable_key(cfg["splits"]["master_seed"], "orcas-group-split", value))
            midpoint = len(ordered) // 2
            scheduling_half, heldout_half = ordered[:midpoint], ordered[midpoint:]
            cal_fit = scheduling_half[:512]
            cal_check = scheduling_half[512:1024]
            tune = scheduling_half[1024:1536]
            schedule = scheduling_half[1536:]
            eval_groups = heldout_half[:10_000]
            roles = {"schedule": schedule, "cal_fit": cal_fit, "cal_check": cal_check,
                     "tune": tune, "eval": eval_groups}
            write_json(stage / "splits/query_roles.json", {
                "seed": cfg["splits"]["master_seed"], "roles": roles,
                "query_policy": "ORCAS-normalized-group-static-v1",
                "hash": digest(roles), "calibration_available": True,
                "heldout_available": len(heldout_half), "excluded_dev_groups": excluded_group_count})
            _write_orcas_query_rows(db, stage)
            _write_orcas_source_queries(db, stage)
            _write_orcas_edges(db, stage)
            source_query_ids = db.execute("select count(*) from source_queries").fetchone()[0]
        for temporary in (db_path, Path(str(db_path) + "-wal"), Path(str(db_path) + "-shm")):
            temporary.unlink(missing_ok=True)
        _empty_qrels(stage / "qrels.parquet")
        counts = {"documents": docs_manifest["counts"]["documents"], "raw_records": raw_records,
                  "records": raw_records, "source_query_ids": source_query_ids,
                  "empty_query_records": empty_query_records,
                  "query_groups": len(group_ids), "eligible_groups": len(ordered),
                  "excluded_dev_groups": excluded_group_count, "unique_edges": unique_edges,
                  "missing_documents": missing_documents, "duplicate_edges": duplicate_edges,
                  "role_groups": {key: len(value) for key, value in roles.items()},
                  "documents_ref": "../msmarco-docs-v1"}
        if counts["records"] != spec["records"] or counts["source_query_ids"] != spec["source_queries"]:
            raise ValueError(f"{name}: registry count mismatch: {counts}")
        manifest = {"dataset_id": name, "status": "VALIDATED", "parser_version": "orcas-static-v1",
                    "downloaded_at": datetime.now(timezone.utc).isoformat(),
                    "source": {"url": spec["url"], "registry": spec["source"],
                               "license": spec["license"], "file": {"bytes": raw_file.stat().st_size,
                               "sha256": file_digest(raw_file), "source_md5": spec["md5"]}},
                    "counts": counts, "files": _artifact_manifest(stage),
                    "split_hash": digest(roles),
                    "row_policy": "group-and-document-row-v2-empty-query-preserved",
                    "documents_release_hash": docs_manifest["release_hash"]}
        manifest["release_hash"] = digest(manifest)
        write_json(stage / "manifest.json", manifest)
        output.parent.mkdir(parents=True, exist_ok=True)
        if output.exists():
            raise ValueError("Unfinished processed ORCAS output exists; refusing overwrite")
        stage.rename(output)
        return read_json(output / "manifest.json")
    except Exception:
        raise


def prepare_scale_dataset(name, cfg, root):
    spec = dataset_spec(name, root)
    output = Path(cfg["paths"]["data"]) / "processed" / name
    with file_lock(output.parent / f".{name}.prepare.lock"):
        if (output / "manifest.json").exists():
            return read_json(output / "manifest.json")
        if spec["parser"] == "msmarco_documents":
            return _prepare_msmarco(name, cfg, root, spec)
        if spec["parser"] == "orcas":
            return _prepare_orcas(name, cfg, root, spec)
        raise ValueError(f"Unknown scale parser: {spec['parser']}")
