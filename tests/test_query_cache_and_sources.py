
import numpy as np
import pytest

from mixindex.config import load_config
from mixindex.data.store import Document
from mixindex.experiments import source_hash
from mixindex.hf_sync import snapshot_source
from mixindex.io import file_digest, read_json, write_json
from mixindex.vectors import encode_corpus, encode_query_pool


def test_query_cache_checks_identity_order_and_integrity(tmp_path, monkeypatch):
    from mixindex import encoders
    calls = []
    class Encoder:
        cost = {"calls": 1}
        def encode_queries(self, texts):
            calls.append(texts)
            return np.array([[1, 0] if text == "first" else [0, 1] for text in texts], dtype=np.float32)
        def close(self):
            pass
    monkeypatch.setattr(encoders, "build_encoder", lambda *args: Encoder())
    cfg = load_config()
    spec = {"dim": 2, "repo_id": "fixture", "resolved_revision": "fixed"}
    path = tmp_path / "queries"
    original, meta = encode_query_pool(["q1", "q2"], ["first", "second"], spec, cfg, path)
    reused, second = encode_query_pool(["q1", "q2"], ["first", "second"], spec, cfg, path)
    assert np.array_equal(original, reused) and len(calls) == 1
    assert not meta["cache_hit"] and second["cache_hit"]
    with pytest.raises(ValueError, match="mismatch"):
        encode_query_pool(["q2", "q1"], ["second", "first"], spec, cfg, path)
    with (path / "queries.npy").open("ab") as file:
        file.write(b"corruption")
    with pytest.raises(ValueError, match="mismatch"):
        encode_query_pool(["q1", "q2"], ["first", "second"], spec, cfg, path)


def test_new_profiles_and_queued_jobs_do_not_change_closed_scientific_source(tmp_path):
    root = tmp_path / "root"
    (root / "src").mkdir(parents=True)
    (root / "src/example.py").write_text("value = 1\n")
    (root / "configs").mkdir()
    (root / "configs/base.yaml").write_text("phase: development\n")
    initial = source_hash(root)
    snapshot_source(root, tmp_path / "run")
    (root / "configs/locked").mkdir()
    (root / "configs/locked/tuning.lock.yaml").write_text("profiles: {}\n")
    (root / "configs/jobs.yaml").write_text("jobs: []\n")
    assert source_hash(root) == initial
    assert source_hash(tmp_path / "run/source") == initial
    # Scientific source edits still invalidate the match.
    (root / "src/example.py").write_text("value = 2\n")
    assert source_hash(root) != initial


def test_corpus_encoding_resumes_only_verified_contiguous_shards(tmp_path):
    documents = [Document(row, f"d{row}", f"text-{row}") for row in range(4)]

    class Data:
        def __len__(self):
            return len(documents)

        def iter_batches(self, batch_size=256):
            yield documents

    class Encoder:
        batch_size = 2
        cost = {"calls": 0}
        spec = {"dim": 2}

        def __init__(self):
            self.calls = []

        def encode_documents(self, texts):
            self.calls.append(list(texts))
            return np.array([[1, 0] if text.endswith("0") or text.endswith("2")
                             else [0, 1] for text in texts], dtype=np.float32)

    output = tmp_path / "vectors"
    output.mkdir()
    first = np.array([[1, 0], [0, 1]], dtype=np.float32)
    first_path = output / "vectors-000000000.npy"
    np.save(first_path, first)
    write_json(output / "progress.json", {
        "status": "RUNNING", "cache_key": "resume-key", "rows_total": 4,
        "dim": 2, "rows_completed": 2, "shards": [{
            "path": first_path.name, "start": 0, "end": 2,
            "sha256": file_digest(first_path),
        }],
    })

    encoder = Encoder()
    store = encode_corpus(Data(), encoder, output, "resume-key", shard_bytes=16)

    assert encoder.calls == [["text-2", "text-3"]]
    assert store.manifest["rows"] == 4
    assert store.manifest["shards"][0]["start"] == 0
    assert store.manifest["shards"][-1]["end"] == 4
    assert read_json(output / "progress.json")["status"] == "COMPLETE"
