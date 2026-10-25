import gzip
import hashlib
import io
import json
from datetime import datetime, timedelta
import tarfile

import lz4.frame
import pyarrow.parquet as pq

from mixindex.config import load_config, project_root
import mixindex.data.prepare as prepare
from mixindex.data.publish import stage_aol_payload
from mixindex.experiments_e6 import _day_sensitivity, _user_block_bootstrap
from mixindex.io import file_digest


def _fixture_config(tmp_path):
    config = load_config()
    config["paths"] = {key: str(tmp_path / key) for key in config["paths"]}
    return config


def _write_fixture_source(tmp_path):
    raw = tmp_path / "data/raw/aol-ia"
    docs = raw / "downloaded_docs"
    docs.mkdir(parents=True)
    (docs / "_done").touch()

    records = []
    for index in range(4):
        url = f"http://example.test/doc-{index}"
        doc_id = hashlib.md5(url.encode()).hexdigest()[:12]
        records.append({
            "doc_id": doc_id, "url": url,
            "wb_url": f"https://web.archive.org/web/20060301/{url}",
            "title": f"Document {index}", "text": f"body {index}",
        })
    with (docs / "a.jsonl.lz4").open("wb") as stream:
        stream.write(lz4.frame.compress(
            b"".join(json.dumps(record).encode() + b"\n" for record in records)))
    with gzip.open(raw / "aol.id2wb.tsv.gz", "wt") as stream:
        for record in records:
            stream.write(f"{record['doc_id']}\t{record['url']}\t{record['wb_url']}\n")

    lines = ["AnonID\tQuery\tQueryTime\tItemRank\tClickURL"]
    start = datetime(2006, 3, 1)
    for week in range(8):
        timestamp = (start + timedelta(days=week * 7)).strftime("%Y-%m-%d %H:%M:%S")
        user = f"fixture-user-{week}"
        for event in range(2):
            url = records[(week + event) % len(records)]["url"]
            lines.append(f"{user}\tquery {week} {event}\t{timestamp}\t1\t{url}")
    payload = ("\n".join(lines) + "\n").encode()
    archive = raw / "aol-data.tar.gz"
    with tarfile.open(archive, "w:gz") as bundle:
        info = tarfile.TarInfo("AOL-user-ct-collection/user-ct-test-collection-01.txt.gz")
        compressed = gzip.compress(payload)
        info.size = len(compressed)
        bundle.addfile(info, io.BytesIO(compressed))


def test_aol_recovery_parser_publishes_capped_temporal_release(tmp_path, monkeypatch):
    _write_fixture_source(tmp_path)
    monkeypatch.setattr(prepare, "AOL_DOCUMENT_CAP", 4)
    monkeypatch.setattr(prepare, "AOL_EVENT_CAP", 2)
    monkeypatch.setattr(prepare, "AOL_ARCHIVE_MD5", file_digest(
        tmp_path / "data/raw/aol-ia/aol-data.tar.gz", "md5"))
    monkeypatch.setattr(prepare, "AOL_ID2WB_MD5", file_digest(
        tmp_path / "data/raw/aol-ia/aol.id2wb.tsv.gz", "md5"))
    config = _fixture_config(tmp_path)

    manifest = prepare.prepare_dataset("aol-ia", config, project_root())
    prepared = tmp_path / "data/processed/aol-ia"

    assert manifest["status"] == "VALIDATED"
    assert manifest["counts"]["documents"] == 4
    assert manifest["counts"]["recovered_documents"] == 4
    assert manifest["counts"]["selected_events"] == 16
    assert manifest["counts"]["selected_events_by_week"] == {str(week): 2 for week in range(8)}
    assert manifest["temporal_policy"]["future_leakage"] == "forbidden"

    events = pq.read_table(prepared / "temporal_events.parquet").to_pylist()
    assert len(events) == 16
    assert {row["week"] for row in events} == set(range(8))
    assert all(len(row["user_cluster"]) == 64 for row in events)
    assert all(f"fixture-user-{week}" not in row["user_cluster"] for week in range(8)
               for row in events)

    payload = tmp_path / "public-aol"
    selected = stage_aol_payload(prepared, payload, manifest)
    public_events = pq.read_table(payload / "temporal_events_redacted.parquet")
    assert "temporal_events_redacted.parquet" in selected
    assert "query_text" not in public_events.column_names
    assert not (payload / "queries.parquet").exists()
    assert not (payload / "documents.jsonl").exists()


def test_e6_primary_sensitivity_uses_user_blocks_and_days():
    events = [
        {"week": 7, "group_id": "g0", "user_cluster": "u0",
         "timestamp": "2006-04-19 00:00:00"},
        {"week": 7, "group_id": "g0", "user_cluster": "u1",
         "timestamp": "2006-04-19 01:00:00"},
        {"week": 7, "group_id": "g1", "user_cluster": "u1",
         "timestamp": "2006-04-20 00:00:00"},
        {"week": 7, "group_id": "g1", "user_cluster": "u2",
         "timestamp": "2006-04-20 01:00:00"},
        {"week": 7, "group_id": "g2", "user_cluster": "u2",
         "timestamp": "2006-04-20 02:00:00"},
        {"week": 7, "group_id": "g2", "user_cluster": "u0",
         "timestamp": "2006-04-20 03:00:00"},
    ]
    metrics = [
        {"week": 7, "group_id": "g0", "arr_at_10": 1.0, "weight": 2.0},
        {"week": 7, "group_id": "g1", "arr_at_10": 0.5, "weight": 2.0},
        {"week": 7, "group_id": "g2", "arr_at_10": 0.0, "weight": 2.0},
    ]

    bootstrap = _user_block_bootstrap(events, metrics, 7, 128, 101)
    sensitivity = _day_sensitivity(events, metrics, 7)

    assert bootstrap["method"] == "user_block_bootstrap_v1"
    assert bootstrap["blocks"] == 3
    assert bootstrap["draws"] == 128
    assert bootstrap["ci95_low"] <= bootstrap["estimate"] <= bootstrap["ci95_high"]
    assert sensitivity["method"] == "leave_one_day_out_v1"
    assert sensitivity["days"] == 2
    assert sensitivity["status"] == "PASS"
