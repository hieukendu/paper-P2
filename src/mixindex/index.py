"""Calibrated exact/HNSW search over one consistent stored-vector snapshot."""

from contextlib import contextmanager
from dataclasses import asdict, dataclass
import importlib.metadata
from pathlib import Path
import threading

import numpy as np

from .calibration import Calibration, calibrate_scores
from .encoders import validate_vectors
from .io import read_json, write_json


class ReadWriteLock:
    def __init__(self):
        self.condition = threading.Condition()
        self.readers = 0
        self.writer = False
        self.waiting_writers = 0

    @contextmanager
    def read(self):
        with self.condition:
            self.condition.wait_for(lambda: not self.writer and not self.waiting_writers)
            self.readers += 1
        try:
            yield
        finally:
            with self.condition:
                self.readers -= 1
                self.condition.notify_all()

    @contextmanager
    def write(self):
        with self.condition:
            self.waiting_writers += 1
            self.condition.wait_for(lambda: not self.writer and self.readers == 0)
            self.waiting_writers -= 1
            self.writer = True
        try:
            yield
        finally:
            with self.condition:
                self.writer = False
                self.condition.notify_all()


@dataclass
class SearchResult:
    rows: np.ndarray
    scores: np.ndarray
    candidates: list[np.ndarray]
    epoch: int


class ExactIndex:
    def __init__(self, vectors, ids, fidelity=None, calibration=None, chunk_rows=16384):
        validate_vectors(np.asarray(vectors))
        if len(ids) != len(vectors) or len(set(ids)) != len(ids):
            raise ValueError("Index IDs must be unique and row aligned")
        self.vectors = np.array(vectors, dtype=np.float32, copy=True)
        self.ids = np.asarray(ids, dtype=str)
        self.id_order = np.argsort(np.argsort(self.ids))
        self.fidelity = np.zeros(len(ids), dtype=bool) if fidelity is None else np.array(fidelity, dtype=bool, copy=True)
        if len(self.fidelity) != len(ids):
            raise ValueError("Fidelity row alignment differs")
        self.calibration = calibration or Calibration()
        self.chunk_rows = chunk_rows
        self.epoch = 0
        self.healthy = True
        self.lock = ReadWriteLock()

    def _check(self):
        if not self.healthy:
            raise RuntimeError("FAILED_SNAPSHOT: restore a complete checkpoint before serving")

    def _top(self, scores, rows, count):
        if len(rows) > count:
            threshold = np.partition(scores, len(scores) - count)[-count]
            keep = np.flatnonzero(scores >= threshold)
        else:
            keep = np.arange(len(rows))
        order = np.lexsort((self.id_order[rows[keep]], -scores[keep]))[:count]
        return rows[keep][order], scores[keep][order]

    def _search(self, queries, k, calibrated=True):
        count = min(k + 1, len(self.ids))
        output_rows, output_scores, candidates = [], [], []
        for query in queries:
            best_rows = np.empty(0, dtype=np.int64)
            best_scores = np.empty(0, dtype=np.float32)
            for start in range(0, len(self.ids), self.chunk_rows):
                end = min(len(self.ids), start + self.chunk_rows)
                raw = self.vectors[start:end] @ query
                scores = calibrate_scores(raw, self.fidelity[start:end], self.calibration) if calibrated else raw
                best_rows, best_scores = self._top(np.concatenate([best_scores, scores]),
                                                   np.concatenate([best_rows, np.arange(start, end)]), count)
            output_rows.append(best_rows)
            output_scores.append(best_scores)
            # Exact search considered every stored document.
            candidates.append(best_rows.copy())
        return SearchResult(np.array(output_rows), np.array(output_scores), candidates, self.epoch)

    def search(self, query_vectors, k=10, calibrated=True):
        with self.lock.read():
            self._check()
            return self._search(np.asarray(query_vectors, dtype=np.float32), k, calibrated)

    def commit_index_update(self, rows, new_vectors, fidelity_updates, cal=None, epoch=None):
        rows = np.asarray(rows, dtype=np.int64)
        new_vectors = np.asarray(new_vectors, dtype=np.float32)
        validate_vectors(new_vectors, self.vectors.shape[1])
        if len(rows) != len(new_vectors) or len(set(rows)) != len(rows) or np.any(rows < 0) or np.any(rows >= len(self.ids)):
            raise ValueError("Invalid same-ID update")
        with self.lock.write():
            self._check()
            try:
                self._write_vectors(rows, new_vectors)
                self.fidelity[rows] = fidelity_updates
                if cal is not None:
                    self.calibration = cal
                self.epoch = self.epoch + 1 if epoch is None else epoch
            except Exception:
                self.healthy = False
                raise

    def _write_vectors(self, rows, vectors):
        self.vectors[rows] = vectors

    def save_index(self, path):
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        with self.lock.read():
            self._check()
            np.save(path / "vectors.npy", self.vectors)
            np.save(path / "fidelity.npy", self.fidelity)
            np.save(path / "ids.npy", self.ids)
            metadata = {"epoch": self.epoch, "calibration": asdict(self.calibration),
                        "chunk_rows": self.chunk_rows, "backend": "exact"}
            self._save_backend(path, metadata)
            write_json(path / "index.json", metadata)

    def _save_backend(self, path, metadata):
        pass


class HnswIndex(ExactIndex):
    def __init__(self, vectors, ids, fidelity=None, calibration=None, chunk_rows=16384,
                 candidates=100, ef_search=200, M=16, ef_construction=200, threads=1, seed=17):
        if importlib.metadata.version("hnswlib") != "0.9.0":
            raise RuntimeError("E0_DEPENDENCY: hnswlib v0.9.0 is required")
        if candidates < 11 or ef_search < candidates:
            raise ValueError("HNSW needs L >= 11 and ef >= L")
        super().__init__(vectors, ids, fidelity, calibration, chunk_rows)
        import hnswlib
        self.parameters = {"candidates": candidates, "ef_search": ef_search, "M": M,
                           "ef_construction": ef_construction, "threads": threads, "seed": seed}
        self.graph = hnswlib.Index(space="ip", dim=self.vectors.shape[1])
        self.graph.init_index(max_elements=len(ids), ef_construction=ef_construction, M=M, random_seed=seed)
        self.graph.set_num_threads(threads)
        self.graph.add_items(self.vectors, np.arange(len(ids)))
        self.graph.set_ef(ef_search)

    def _search(self, queries, k, calibrated=True):
        labels, distances = self.graph.knn_query(queries, k=min(self.parameters["candidates"], len(self.ids)))
        count = min(k + 1, len(self.ids))
        rows, scores = [], []
        for candidates, distance in zip(labels, distances):
            raw = 1 - distance
            values = calibrate_scores(raw, self.fidelity[candidates], self.calibration) if calibrated else raw
            best_rows, best_scores = self._top(values, candidates.astype(np.int64), count)
            rows.append(best_rows)
            scores.append(best_scores)
        return SearchResult(np.array(rows), np.array(scores), [c.astype(np.int64) for c in labels], self.epoch)

    def _write_vectors(self, rows, vectors):
        self.graph.add_items(vectors, rows)  # Stock same-ID graph update, under writer lock.
        self.vectors[rows] = vectors

    def _save_backend(self, path, metadata):
        self.graph.save_index(str(path / "hnsw.bin"))
        metadata.update(backend="hnsw", parameters=self.parameters)


def load_index(path):
    path = Path(path)
    meta = read_json(path / "index.json")
    vectors = np.load(path / "vectors.npy", allow_pickle=False)
    ids = np.load(path / "ids.npy", allow_pickle=False)
    fidelity = np.load(path / "fidelity.npy", allow_pickle=False)
    cal = Calibration(**meta["calibration"])
    if meta["backend"] == "hnsw":
        # Avoid constructing an unused fresh graph during restore.
        import hnswlib
        index = HnswIndex.__new__(HnswIndex)
        ExactIndex.__init__(index, vectors, ids, fidelity, cal, meta["chunk_rows"])
        index.parameters = meta["parameters"]
        index.graph = hnswlib.Index(space="ip", dim=vectors.shape[1])
        index.graph.load_index(str(path / "hnsw.bin"), max_elements=len(ids))
        index.graph.set_ef(index.parameters["ef_search"])
        index.graph.set_num_threads(index.parameters["threads"])
        if index.graph.get_current_count() != len(ids):
            raise ValueError("Restored HNSW population differs")
        if not np.allclose(index.graph.get_items(np.arange(len(ids))), vectors, atol=1e-6):
            raise ValueError("Restored HNSW vectors differ from stored snapshot")
    else:
        index = ExactIndex(vectors, ids, fidelity, cal, meta["chunk_rows"])
    index.epoch = meta["epoch"]
    return index


def validate_ann_snapshot(index, exact_index, Q_tune):
    ann, exact = index.search(Q_tune), exact_index.search(Q_tune)
    raw_ann, raw_exact = index.search(Q_tune, calibrated=False), exact_index.search(Q_tune, calibrated=False)
    if not len(ann.rows):
        raise ValueError("Q_tune is empty; cannot certify ANN")
    return {"candidate_recall_at_11": float(np.mean([
                len(set(c) & set(e[:11])) / min(11, len(e)) for c, e in zip(ann.candidates, exact.rows)])),
            "serving_recall_at_10": float(np.mean([
                len(set(a[:10]) & set(e[:10])) / min(10, len(e)) for a, e in zip(ann.rows, exact.rows)])),
            "raw_recall_at_10": float(np.mean([
                len(set(a[:10]) & set(e[:10])) / min(10, len(e)) for a, e in zip(raw_ann.rows, raw_exact.rows)]))}
