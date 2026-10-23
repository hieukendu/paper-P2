"""Publish a prepared BEIR release only after full ingestion and ID checks."""

import csv
from datetime import date, datetime, timezone
from collections import Counter, defaultdict
import gzip
import hashlib
import heapq
import json
from pathlib import Path
import sqlite3
import tarfile
import tempfile
import unicodedata

import pyarrow as pa
import pyarrow.parquet as pq

from ..io import digest, file_digest, file_lock, read_json, write_json
from .download import dataset_spec, download_dataset, extract_beir, verify_source_file
from .splits import build_static_splits, group_queries, stable_key
from .store import DocumentStore, build_document_store


def iter_source_documents(path):
    with Path(path).open() as f:
        for line in f:
            record = json.loads(line)
            if not isinstance(record.get("_id"), str) or not isinstance(record.get("text"), str):
                raise ValueError("Invalid BEIR document schema")
            yield record["_id"], record.get("title", ""), record["text"]


AOL_DOCUMENT_CAP = 50_000
AOL_EVENT_CAP = 50_000
AOL_WEEKS = 8
AOL_START_DATE = date(2006, 3, 1)
AOL_SOURCE_URL = "https://archive.org/download/aolsearchdata2006/aol-data.tar.gz"
AOL_OFFICIAL_SOURCE_URL = "https://ir-datasets.com/aol-ia.html"
AOL_ARCHIVE_MD5 = "31cd27ce12c3a3f2df62a38050ce4c0a"
AOL_ID2WB_MD5 = "afbf9b03e1a0fabc9f3fdd5105e6ae5a"


def _iter_aol_log_records(archive_path):
    """Yield normalized AOL log rows without exposing raw user IDs downstream."""
    archive_path = Path(archive_path)
    with tarfile.open(archive_path, mode="r:gz") as archive:
        members = sorted(
            (member for member in archive.getmembers()
             if member.name.endswith(".txt.gz") and member.isfile()),
            key=lambda member: member.name,
        )
        if not members:
            raise ValueError("AOL_SOURCE_INVALID: archive has no compressed query-log members")
        for member in members:
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError(f"AOL_SOURCE_INVALID: cannot read {member.name}")
            with stream, gzip.GzipFile(fileobj=stream) as compressed:
                for raw in compressed:
                    line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                    if line.startswith("AnonID\tQuery\tQueryTime\tItemRank\tClickURL"):
                        continue
                    fields = line.split("\t", 4)
                    if len(fields) != 5:
                        raise ValueError(f"AOL_SOURCE_INVALID: malformed row in {member.name}")
                    user_id, query, timestamp, rank, url = fields
                    if not user_id or not timestamp:
                        raise ValueError(f"AOL_SOURCE_INVALID: missing user/time in {member.name}")
                    try:
                        parsed_time = datetime.fromisoformat(timestamp)
                    except ValueError as exc:
                        raise ValueError("AOL_SOURCE_INVALID: invalid timestamp") from exc
                    parsed_rank = int(rank) if rank else None
                    normalized = " ".join(unicodedata.normalize("NFKC", query).casefold().split())
                    yield {
                        "user_id": user_id,
                        "query": normalized,
                        "query_id": hashlib.md5(normalized.encode()).hexdigest()[:14],
                        "timestamp": parsed_time,
                        "rank": parsed_rank,
                        "url": url or None,
                    }


def _iter_aol_recovered_documents(path):
    """Read aolia-tools JSONL/LZ4 shards in a deterministic file order."""
    try:
        from lz4 import frame
    except ImportError as exc:
        raise RuntimeError("AOL_RECOVERY_DEPENDENCY_MISSING: install lz4") from exc
    files = sorted(Path(path).glob("*.jsonl.lz4"))
    if not files:
        raise ValueError("AOL_RECOVERY_MISSING: no aolia-tools document shards found")
    for file in files:
        with frame.open(file, mode="rb") as stream:
            for line in stream:
                record = json.loads(line)
                if not all(isinstance(record.get(key), str) for key in
                           ("doc_id", "title", "text", "url", "wb_url")):
                    raise ValueError(f"AOL_RECOVERY_INVALID: malformed document in {file.name}")
                expected_id = hashlib.md5(record["url"].encode()).hexdigest()[:12]
                if record["doc_id"] != expected_id:
                    raise ValueError(f"AOL_RECOVERY_INVALID: document ID/URL mismatch in {file.name}")
                yield record


def _select_aol_documents(downloaded_path, cap, seed):
    """Select the smallest stable hashes without holding the full corpus in RAM."""
    heap = []
    for record in _iter_aol_recovered_documents(downloaded_path):
        key = int(hashlib.sha256(
            f"{seed}\0AOL-uniform-document\0{record['doc_id']}".encode()).hexdigest(), 16)
        item = (-key, record["doc_id"])
        if len(heap) < cap:
            heapq.heappush(heap, item)
        elif key < -heap[0][0]:
            heapq.heapreplace(heap, item)
    selected = {doc_id for _, doc_id in heap}
    if len(selected) != cap:
        raise ValueError(f"AOL_RECOVERY_INSUFFICIENT: recovered={len(selected)} required={cap}")
    return selected


def _aol_user_cluster(user_id):
    return hashlib.sha256(f"aol-user-cluster-v1\0{user_id}".encode()).hexdigest()


def _write_aol_parquet(path, rows, schema):
    import pyarrow as pa
    import pyarrow.parquet as pq
    pq.write_table(pa.Table.from_pylist(rows, schema=schema), path, compression="zstd")


def prepare_aol_dataset(cfg, root):
    """Prepare the real AOL-IA corpus and a capped chronological event release."""
    import pyarrow as pa

    root = Path(root)
    output = Path(cfg["paths"]["data"]) / "processed" / "aol-ia"
    if (output / "manifest.json").exists():
        return validate_prepared(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError("AOL_PREPARE_INCOMPLETE: refusing to overwrite an existing release")
    raw = Path(cfg["paths"]["data"]) / "raw" / "aol-ia"
    archive_path = raw / "aol-data.tar.gz"
    id2wb_path = raw / "aol.id2wb.tsv.gz"
    recovery_options = ((raw / "downloaded_docs_targeted", "http-targeted"),
                        (raw / "downloaded_docs_http", "http"),
                        (raw / "downloaded_docs", "https"))
    completed_recovery = [(path, transport) for path, transport in recovery_options
                          if (path / "_done").exists()]
    if not archive_path.exists():
        raise ValueError("AOL_SOURCE_MISSING: aol-data.tar.gz is not downloaded")
    if not id2wb_path.exists():
        raise ValueError("AOL_SOURCE_MISSING: aol.id2wb.tsv.gz is not downloaded")
    if file_digest(archive_path, "md5") != AOL_ARCHIVE_MD5:
        raise ValueError("AOL_SOURCE_INVALID: query-log archive checksum differs")
    if file_digest(id2wb_path, "md5") != AOL_ID2WB_MD5:
        raise ValueError("AOL_SOURCE_INVALID: id2wb checksum differs")
    if not completed_recovery:
        raise ValueError("AOL_RECOVERY_INCOMPLETE: aolia-tools has not recovered all documents")
    downloaded_path, recovery_transport = completed_recovery[0]
    recovery_metadata = {}
    recovery_metadata_path = downloaded_path / "recovery_metadata.json"
    if recovery_metadata_path.exists():
        recovery_metadata = json.loads(recovery_metadata_path.read_text())
        if recovery_metadata.get("published") is not False:
            raise ValueError("AOL_RECOVERY_INVALID: candidate metadata is publishable")

    seed = int(cfg["splits"]["master_seed"])
    selected_doc_ids = _select_aol_documents(downloaded_path, AOL_DOCUMENT_CAP, seed)
    selected_records = {}
    recovered_documents = 0
    for record in _iter_aol_recovered_documents(downloaded_path):
        recovered_documents += 1
        if record["doc_id"] in selected_doc_ids:
            selected_records[record["doc_id"]] = record
    if len(selected_records) != AOL_DOCUMENT_CAP:
        raise ValueError("AOL_RECOVERY_INSUFFICIENT: selected document records are incomplete")

    first_time = None
    last_time = None
    source_events = 0
    source_users = set()
    week_counts = {week: Counter() for week in range(AOL_WEEKS)}
    source_events_by_week = Counter()
    for record in _iter_aol_log_records(archive_path):
        source_events += 1
        source_users.add(record["user_id"])
        first_time = record["timestamp"] if first_time is None else min(first_time, record["timestamp"])
        last_time = record["timestamp"] if last_time is None else max(last_time, record["timestamp"])
        # The official AOL-IA release starts on 2006-03-01; count temporal
        # blocks in the same pass as source coverage so preparation needs only
        # one source scan for statistics and one for the selected events.
        week = (record["timestamp"].date() - AOL_START_DATE).days // 7
        if 0 <= week < AOL_WEEKS:
            week_counts[week][record["user_id"]] += 1
            source_events_by_week[week] += 1
    if first_time is None or last_time is None:
        raise ValueError("AOL_SOURCE_INVALID: query log is empty")
    if first_time.date() != AOL_START_DATE:
        raise ValueError("AOL_SOURCE_INVALID: unexpected chronology start date")
    start_date = AOL_START_DATE
    selected_users = {}
    selected_counts = {}
    for week in range(AOL_WEEKS):
        total = 0
        users = set()
        ordered = sorted(
            week_counts[week],
            key=lambda user: stable_key(seed, f"AOL-week-{week}-user", user),
        )
        for user in ordered:
            count = week_counts[week][user]
            if total + count <= AOL_EVENT_CAP:
                users.add(user)
                total += count
        selected_users[week] = users
        selected_counts[week] = total
    if any(selected_counts[week] == 0 for week in range(AOL_WEEKS)):
        raise ValueError("AOL_TEMPORAL_COVERAGE_FAILED: one or more weeks has no selected events")

    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".aol-", dir=output.parent))
    try:
        build_document_store(
            ((doc_id, selected_records[doc_id]["title"], selected_records[doc_id]["text"])
             for doc_id in sorted(selected_records)), stage)
        local_doc_rows = {doc_id: row for row, doc_id in enumerate(sorted(selected_records))}
        events = []
        query_text = {}
        source_order = 0
        for record in _iter_aol_log_records(archive_path):
            week = (record["timestamp"].date() - start_date).days // 7
            if week < 0 or week >= AOL_WEEKS or record["user_id"] not in selected_users[week]:
                continue
            query_id = record["query_id"]
            group_id = hashlib.sha256(record["query"].encode()).hexdigest()
            query_text[query_id] = record["query"]
            clicked_doc_id = (hashlib.md5(record["url"].encode()).hexdigest()[:12]
                              if record["url"] else None)
            events.append({
                "source_order": source_order,
                "week": week,
                "timestamp": record["timestamp"].isoformat(sep=" "),
                "user_cluster": _aol_user_cluster(record["user_id"]),
                "query_id": query_id,
                "group_id": group_id,
                "query_text": record["query"],
                "doc_id": clicked_doc_id,
                "doc_row": local_doc_rows.get(clicked_doc_id, -1) if clicked_doc_id else -1,
                "rank": record["rank"],
                "clicked": bool(clicked_doc_id),
            })
            source_order += 1
        events.sort(key=lambda row: (row["timestamp"], row["source_order"]))
        for event_id, record in enumerate(events):
            record["event_id"] = event_id
            record.pop("source_order")
        if any(sum(event["week"] == week for event in events) != selected_counts[week]
               for week in range(AOL_WEEKS)):
            raise ValueError("AOL_TEMPORAL_COVERAGE_FAILED: selected event cap changed")

        groups = group_queries(sorted(query_text.items()))
        group_weeks = defaultdict(set)
        for event in events:
            group_weeks[event["group_id"]].add(event["week"])
        future = sorted(group_id for group_id, weeks in group_weeks.items() if max(weeks) >= 1)
        history = sorted(group_id for group_id, weeks in group_weeks.items() if min(weeks) <= 6)
        week_zero = sorted(
            (group_id for group_id, weeks in group_weeks.items() if 0 in weeks),
            key=lambda group_id: stable_key(seed, "AOL-week-zero", group_id),
        )
        cut = max(1, len(week_zero) // 3) if week_zero else 0
        roles = {
            "eval": future,
            "schedule": history,
            "tune": week_zero[:cut],
            "cal_fit": week_zero[cut:2 * cut],
            "cal_check": week_zero[2 * cut:3 * cut],
        }
        write_json(stage / "splits/query_roles.json", {
            "seed": seed, "roles": roles, "weeks": AOL_WEEKS,
            "start_date": start_date.isoformat(), "hash": digest(roles),
            "temporal_policy": "history-before-cutoff-v1",
        })
        _write_aol_parquet(
            stage / "queries.parquet", list(groups.values()),
            pa.schema([("group_id", pa.string()), ("normalized_text", pa.string()),
                       ("text", pa.string()), ("representative_id", pa.string()),
                       ("query_ids", pa.list_(pa.string()))]),
        )
        _write_aol_parquet(
            stage / "temporal_events.parquet", events,
            pa.schema([("event_id", pa.int64()), ("week", pa.int16()),
                       ("timestamp", pa.string()), ("user_cluster", pa.string()),
                       ("query_id", pa.string()), ("group_id", pa.string()),
                       ("query_text", pa.string()), ("doc_id", pa.string()),
                       ("doc_row", pa.int64()), ("rank", pa.int32()),
                       ("clicked", pa.bool_())]),
        )
        qrels = [{"split": f"week-{event['week']}", "query_id": event["query_id"],
                  "group_id": event["group_id"], "doc_id": event["doc_id"],
                  "doc_row": event["doc_row"], "grade": int(event["clicked"]),
                  "week": event["week"]}
                 for event in events if event["doc_id"] is not None]
        _write_aol_parquet(
            stage / "qrels.parquet", qrels,
            pa.schema([("split", pa.string()), ("query_id", pa.string()),
                       ("group_id", pa.string()), ("doc_id", pa.string()),
                       ("doc_row", pa.int64()), ("grade", pa.int32()),
                       ("week", pa.int16())]),
        )
        clicked = [event for event in events if event["clicked"]]
        in_pool = [event for event in clicked if event["doc_row"] >= 0]
        source = {
            "official_dataset": AOL_OFFICIAL_SOURCE_URL,
            "archive_source": AOL_SOURCE_URL,
            "archive_file": {"bytes": archive_path.stat().st_size,
                              "sha256": file_digest(archive_path),
                              "md5": file_digest(archive_path, "md5")},
            "id2wb_file": {"bytes": id2wb_path.stat().st_size,
                           "sha256": file_digest(id2wb_path),
                           "md5": file_digest(id2wb_path, "md5")},
            "recovery_tool": "terrierteam/aolia-tools",
            "recovery_transport": recovery_transport,
            "recovery_directory": downloaded_path.name,
        }
        if recovery_metadata:
            source["recovery_scope"] = {
                "scope": recovery_metadata.get("scope"),
                "selection": recovery_metadata.get("selection"),
                "seed": recovery_metadata.get("seed"),
                "candidate_documents": recovery_metadata.get("candidate_documents"),
                "candidate_sha256": recovery_metadata.get("candidate_sha256"),
                "published": False,
            }
        counts = {
            "documents": AOL_DOCUMENT_CAP, "recovered_documents": recovered_documents,
            "source_events": source_events, "source_users": len(source_users),
            "selected_events": len(events), "selected_events_by_week": {
                str(week): sum(event["week"] == week for event in events)
                for week in range(AOL_WEEKS)},
            "source_events_by_week": {str(week): source_events_by_week[week]
                                       for week in range(AOL_WEEKS)},
            "clicked_events": len(clicked), "clicked_docs_in_pool": len(in_pool),
            "clicked_doc_pool_coverage": len(in_pool) / len(clicked) if clicked else 0.0,
            "weeks": AOL_WEEKS, "start_date": start_date.isoformat(),
            "end_date": last_time.date().isoformat(),
        }
        if recovery_metadata:
            counts["recovery_candidate_documents"] = recovery_metadata.get(
                "candidate_documents")
        artifacts = {}
        for file in sorted(stage.rglob("*")):
            if file.is_file():
                artifacts[str(file.relative_to(stage))] = {
                    "bytes": file.stat().st_size, "sha256": file_digest(file)}
        manifest = {
            "dataset_id": "aol-ia", "status": "VALIDATED", "parser_version": "aol-ia-v1",
            "downloaded_at": datetime.now(timezone.utc).isoformat(), "source": source,
            "counts": counts, "files": artifacts,
            "split_hash": digest(roles), "text_policy": "title-newline-body-v1",
            "row_policy": "stable-document-id-hash-v1", "temporal_policy": {
                "weeks": AOL_WEEKS, "event_cap": AOL_EVENT_CAP,
                "sampling": "stable-user-block-within-week-v1",
                "future_leakage": "forbidden", "user_output": "opaque-cluster-only",
            },
        }
        manifest["release_hash"] = digest(manifest)
        write_json(stage / "manifest.json", manifest)
        if output.exists():
            raise ValueError("AOL_PREPARE_OUTPUT_EXISTS: preserving existing output")
        stage.rename(output)
        return validate_prepared(output)
    except Exception:
        # Preserve the immutable raw source but do not publish a partial processed release.
        import shutil
        shutil.rmtree(stage, ignore_errors=True)
        raise


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
    if spec["parser"] == "aol_recovery":
        return prepare_aol_dataset(cfg, root)
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
