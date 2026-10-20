import json

import pyarrow.parquet as pq
import pytest

from mixindex.data.publish import stage_document_parquet, verify_document_parquet
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
