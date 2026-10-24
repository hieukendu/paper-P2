import threading

import numpy as np
import torch

from mixindex.calibration import Calibration
from mixindex.encoders import EncoderAdapter
from mixindex.index import ExactIndex
from mixindex.maps import normalize
from mixindex.runtime import probe_encoder


def test_token_bucketing_preserves_rows_and_reports_actual_padded_batches():
    # Character length and token length deliberately disagree.
    texts = ["one", "a very long character string", "eight", "third"]
    length = dict(zip(texts, [9, 1, 8, 3]))
    values = {text: vector for text, vector in zip(texts, normalize(np.array([[1, 2], [2, 1], [1, 1], [-1, 2]])))}
    batches = []
    class Model:
        def tokenizer(self, prepared, **kwargs):
            return {"input_ids": [list(range(length[text])) for text in prepared]}
        def encode(self, prepared, **kwargs):
            batches.append(prepared)
            return np.stack([values[text] for text in prepared])
    encoder = EncoderAdapter.__new__(EncoderAdapter)
    encoder.model, encoder.torch, encoder.device = Model(), torch, "cpu"
    encoder.spec = {"dim": 2, "max_tokens": 10, "document_prefix": ""}
    encoder.batch_size = 2
    encoder.cost = {"calls": 0, "documents": 0, "nonpad_tokens": 0, "padded_tokens": 0,
                    "truncated_documents": 0, "wall_seconds": 0.0}
    result = encoder.encode_documents(texts)
    assert np.array_equal(result, np.stack([values[text] for text in texts]))
    assert batches == [["one", "eight"], ["third", "a very long character string"]]
    assert encoder.cost["padded_tokens"] == 24 and encoder.cost["nonpad_tokens"] == 21
    assert encoder.cost["calls"] == 2


def test_runtime_probe_records_oom_and_restores_runtime_settings():
    class Encoder:
        batch_size = 8
        device = "cpu"
        spec = {"dim": 2}
        def __init__(self):
            self.cost = {"calls": 0, "nonpad_tokens": 0, "padded_tokens": 0, "truncated_documents": 0}
        def encode_documents(self, texts):
            if self.batch_size == 4:
                raise torch.cuda.OutOfMemoryError("probe fixture")
            self.cost["calls"] += 1
            self.cost["nonpad_tokens"] += len(texts)
            self.cost["padded_tokens"] += len(texts)
            return np.repeat(np.array([[1.0, 0]], dtype=np.float32), len(texts), axis=0)
    encoder = Encoder()
    probe = probe_encoder(encoder, ["x", "y"], [1, 2, 4], repeats=3)
    assert encoder.batch_size == 8
    assert probe["selected_batch_size"] in {1, 2}
    assert [r["status"] for r in probe["table"]] == ["PASS", "PASS", "OOM"]
    assert probe["sample_documents"] == 2 and probe["exclusive"] == "unverified"


def test_readers_never_observe_new_vector_with_old_fidelity_or_calibration():
    vectors = normalize(np.random.default_rng(73).normal(size=(12, 3)))
    index = ExactIndex(vectors, list(map(str, range(12))))
    entered, release, query_finished = threading.Event(), threading.Event(), threading.Event()
    write = index._write_vectors
    failures = []
    def paused_write(rows, values):
        write(rows, values)
        entered.set()
        if not release.wait(timeout=3):
            raise RuntimeError("reader/writer fixture timeout")
    index._write_vectors = paused_write
    def update():
        try:
            index.commit_index_update([0], -vectors[:1], True, cal=Calibration(0.5, 0.1))
        except Exception as exc:
            failures.append(exc)
    observed = []
    def query():
        result = index.search(vectors[:1])
        observed.append((result.epoch, bool(index.fidelity[0]), index.calibration))
        query_finished.set()
    writer = threading.Thread(target=update)
    reader = threading.Thread(target=query)
    writer.start()
    assert entered.wait(timeout=2)
    reader.start()
    try:
        assert not query_finished.wait(timeout=0.05)
    finally:
        release.set()
        writer.join(timeout=3)
        reader.join(timeout=3)
    assert not failures and query_finished.is_set()
    assert observed == [(1, True, Calibration(0.5, 0.1))]
