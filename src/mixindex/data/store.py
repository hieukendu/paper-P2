"""On-disk document lookup; source row order is the vector row order."""

from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3


@dataclass(frozen=True)
class Document:
    row: int
    doc_id: str
    text: str


def document_text(title, body):
    return title + "\n" + body if title else body


class DocumentStore:
    def __init__(self, path):
        self.path = Path(path)

    def __len__(self):
        with sqlite3.connect(f"file:{self.path / 'lookup.sqlite'}?mode=ro", uri=True) as db:
            return db.execute("select count(*) from documents").fetchone()[0]

    def get_documents(self, rows):
        result = []
        with sqlite3.connect(f"file:{self.path / 'lookup.sqlite'}?mode=ro", uri=True) as db:
            with (self.path / "documents.jsonl").open("rb") as f:
                for row in rows:
                    found = db.execute("select offset from documents where row_id=?", (int(row),)).fetchone()
                    if found is None:
                        raise IndexError(f"Unknown document row {row}")
                    f.seek(found[0])
                    record = json.loads(f.readline())
                    result.append(Document(int(row), record["doc_id"], record["text"]))
        return result

    def iter_batches(self, batch_size=256):
        batch = []
        with (self.path / "documents.jsonl").open() as f:
            for row, line in enumerate(f):
                record = json.loads(line)
                batch.append(Document(row, record["doc_id"], record["text"]))
                if len(batch) == batch_size:
                    yield batch
                    batch = []
        if batch:
            yield batch


def build_document_store(records, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    if (output / "lookup.sqlite").exists():
        raise ValueError("Document store already exists; refusing to overwrite")
    counts = {"raw_documents": 0, "documents": 0, "duplicate_documents": 0, "empty_documents": 0}
    with sqlite3.connect(output / "lookup.sqlite") as db:
        db.execute("create table documents(doc_id text primary key, row_id integer unique, offset integer)")
        with (output / "documents.jsonl").open("xb+") as f, (output / "doc_ids.txt").open("x") as ids:
            for doc_id, title, body in records:
                if not all(isinstance(v, str) for v in (doc_id, title, body)):
                    raise ValueError("Document ID/title/body must be strings")
                if "\n" in doc_id or "\r" in doc_id or not doc_id:
                    raise ValueError("Invalid document ID")
                counts["raw_documents"] += 1
                text = document_text(title, body)
                existing = db.execute("select offset from documents where doc_id=?", (doc_id,)).fetchone()
                if existing:
                    end = f.tell()
                    f.seek(existing[0])
                    previous = json.loads(f.readline())
                    f.seek(end)
                    if previous["text"] != text:
                        raise ValueError("Conflicting duplicate document ID")
                    counts["duplicate_documents"] += 1
                    continue
                offset = f.tell()
                f.write((json.dumps({"doc_id": doc_id, "text": text}, ensure_ascii=False) + "\n").encode())
                ids.write(doc_id + "\n")
                db.execute("insert into documents values(?,?,?)", (doc_id, counts["documents"], offset))
                counts["documents"] += 1
                counts["empty_documents"] += not bool(text.strip())
    return DocumentStore(output), counts
