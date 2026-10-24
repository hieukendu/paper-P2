"""Calibrated exact/HNSW search over one consistent stored-vector snapshot."""

from contextlib import contextmanager
from dataclasses import asdict, dataclass
import importlib.metadata
from pathlib import Path
import threading
import time

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
        self.parameters = {"candidates": candidates, "ef_search": ef_search, "M": M,
                           "ef_construction": ef_construction, "threads": threads, "seed": seed}
        self.rebuild_count = 0
        self.rebuild_seconds = 0.0
        self.graph = self._new_graph()

    def _new_graph(self):
        import hnswlib
        graph = hnswlib.Index(space="ip", dim=self.vectors.shape[1])
        graph.init_index(max_elements=len(self.ids),
                         ef_construction=self.parameters["ef_construction"],
                         M=self.parameters["M"], random_seed=self.parameters["seed"])
        graph.set_num_threads(self.parameters["threads"])
        graph.add_items(self.vectors, np.arange(len(self.ids)))
        graph.set_ef(self.parameters["ef_search"])
        return graph

    def _rebuild_graph(self):
        started = time.monotonic()
        self.graph = self._new_graph()
        self.rebuild_count += 1
        self.rebuild_seconds += time.monotonic() - started

    def search(self, query_vectors, k=10, calibrated=True):
        queries = np.asarray(query_vectors, dtype=np.float32)
        try:
            with self.lock.read():
                self._check()
                return self._search(queries, k, calibrated)
        except RuntimeError as exc:
            # hnswlib can lose enough reachable candidates after stock same-ID
            # updates that its contiguous result allocation fails.  Rebuild the
            # same fixed-parameter graph under the writer lock, then retry; do
            # not silently substitute exact search or alter the locked grid.
            if "Cannot return the results in a contiguous 2D array" not in str(exc):
                raise
            with self.lock.write():
                self._check()
                self._rebuild_graph()
                return self._search(queries, k, calibrated)

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
        if len(rows):
            self.graph.add_items(vectors, rows)  # Stock same-ID graph update, under writer lock.
        self.vectors[rows] = vectors

    def _save_backend(self, path, metadata):
        self.graph.save_index(str(path / "hnsw.bin"))
        metadata.update(backend="hnsw", parameters=self.parameters,
                        rebuild_count=self.rebuild_count,
                        rebuild_seconds=self.rebuild_seconds)

    def configure_search(self, candidates, ef_search):
        if candidates < 11 or ef_search < candidates:
            raise ValueError("HNSW needs L >= 11 and ef >= L")
        with self.lock.write():
            self._check()
            self.graph.set_ef(ef_search)
            self.parameters.update(candidates=candidates, ef_search=ef_search)


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
        index.rebuild_count = int(meta.get("rebuild_count", 0))
        index.rebuild_seconds = float(meta.get("rebuild_seconds", 0.0))
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


def select_search_config(snapshots, Q_tune, grid, gate=0.99, threads=1, seed=17,
                          transfer=None):
    """Find the smallest declared pair that passes on every comparison variant."""
    if not len(Q_tune):
        inherited = transfer or {"candidates": 100, "ef_search": 200}
        return {**inherited, "status": "UNTUNED_TRANSFER", "table": [],
                "reason": "no_independent_tuning_queries"}
    if not snapshots or not grid:
        raise ValueError("Search tuning needs bootstrap snapshots and a bounded grid")
    candidates = sorted({(int(L), int(ef)) for L, ef in grid})
    if any(L < 11 or ef < L for L, ef in candidates):
        raise ValueError("Invalid search grid")
    table = []
    passing = {pair: True for pair in candidates}
    # Keep one mutable graph at a time, and evaluate every declared pair before selection.
    for name, snapshot in snapshots.items():
        exact = ExactIndex(snapshot.vectors, snapshot.ids, snapshot.fidelity, snapshot.calibration,
                            snapshot.chunk_rows)
        ann = HnswIndex(snapshot.vectors, snapshot.ids, snapshot.fidelity, snapshot.calibration,
                         candidates=candidates[0][0], ef_search=candidates[0][1],
                         threads=threads, seed=seed)
        for L, ef in candidates:
            ann.configure_search(L, ef)
            fidelity = validate_ann_snapshot(ann, exact, Q_tune)
            passed = (fidelity["candidate_recall_at_11"] >= gate and
                      fidelity["serving_recall_at_10"] >= gate)
            table.append({"variant": name, "candidates": L, "ef_search": ef,
                           "status": "PASS" if passed else "FAIL", **fidelity})
            passing[(L, ef)] &= passed
        del ann, exact
    eligible = [pair for pair in candidates if passing[pair]]
    if not eligible:
        return {"status": "ANN_GATE_FAILED", "candidates": None, "ef_search": None,
                "diagnostic_largest": list(candidates[-1]), "table": table}
    L, ef = eligible[0]
    return {"status": "PASS", "candidates": L, "ef_search": ef, "table": table}
