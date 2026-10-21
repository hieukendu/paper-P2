import json
import gzip

import pyarrow.parquet as pq
import pytest

from mixindex.data.publish import (_verify_scale_sources, stage_document_parquet,
                                   stage_scale_payload, verify_document_parquet)
from mixindex.io import file_digest


def test_document_publication_preserves_rows_text_and_file_boundaries(tmp_path):
    rows = [{"doc_id": f"doc{i}", "text": "Title\nUnicode café\t body " + str(i)} for i in range(11)]
    source = tmp_path / "documents.jsonl"
    source.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))
    files = stage_document_parquet(source, tmp_path / "documents", len(rows), rows_per_file=4, batch_rows=3)
    assert len(files) == 3
    restored = [row for file in files for row in pq.read_table(file).to_pylist()]
    assert restored == [{"doc_row": i, **row} for i, row in enumerate(rows)]
    assert [pq.ParquetFile(file).metadata.num_rows for file in files] == [4, 4, 3]
    assert not list((tmp_path / "documents").glob("*.part"))
    with pytest.raises(ValueError, match="row count differs"):
        stage_document_parquet(source, tmp_path / "wrong", 12)
    first = pq.read_table(files[0])
    modified = first.to_pylist()
    modified[0]["text"] = "corruption"
    import pyarrow as pa
    pq.write_table(pa.Table.from_pylist(modified, schema=first.schema), files[0])
    with pytest.raises(ValueError, match="canonical source checksum"):
        verify_document_parquet(files, len(rows), file_digest(source))


def test_scale_publication_payload_preserves_validated_release_and_source_hash(tmp_path):
    source = tmp_path / "processed" / "msmarco-docs-v1"
    source.mkdir(parents=True)
    documents = [{"doc_id": f"D{i}", "text": f"body {i}"} for i in range(3)]
    document_path = source / "documents.jsonl"
    document_path.write_text("".join(json.dumps(row) + "\n" for row in documents))
    for name in ("doc_ids.txt", "queries.parquet", "qrels.parquet", "splits/query_roles.json"):
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fixture\n")
    manifest = {
        "dataset_id": "msmarco-docs-v1",
        "status": "VALIDATED",
        "release_hash": "fixture-release",
        "counts": {"documents": 3, "test_queries": 1, "test_qrels": 1},
        "files": {"documents.jsonl": {"bytes": document_path.stat().st_size,
                                        "sha256": file_digest(document_path)}},
        "text_policy": "title-newline-body-v1",
        "row_policy": "source-ingestion-order",
    }
    (source / "manifest.json").write_text(json.dumps(manifest))
    payload = tmp_path / "payload"
    selected = stage_scale_payload("msmarco-docs-v1", source, payload, manifest,
                                   {"documents.tsv.gz": {"sha256": "fixture"}})
    publication = json.loads((payload / "publication.json").read_text())
    assert "documents/part-00000.parquet" in selected
    assert publication["source_release_hash"] == "fixture-release"
    assert publication["document_rows"] == 3
    assert publication["source_documents_sha256"] == file_digest(document_path)
    assert not list(payload.rglob("*.part"))


def test_orcas_source_record_is_verified_from_manifest_metadata(tmp_path):
    raw = tmp_path / "data" / "raw" / "orcas"
    raw.mkdir(parents=True)
    archive = raw / "orcas.tsv.gz"
    with gzip.open(archive, "wt", encoding="utf-8") as stream:
        stream.write("qid\tquery\tdoc\turl\n")
    source_record = {"bytes": archive.stat().st_size, "sha256": file_digest(archive)}
    manifest = {"source": {"file": source_record}}
    verified = _verify_scale_sources(
        "orcas", {"url": "https://example.test/orcas.tsv.gz", "md5": file_digest(archive, "md5")},
        manifest, tmp_path,
    )
    assert verified["file"] == "orcas.tsv.gz"
    assert verified["bytes"] == source_record["bytes"]
    assert verified["sha256"] == source_record["sha256"]
