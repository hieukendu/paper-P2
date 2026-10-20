"""Immutable vector shards and the sole budgeted path to new document embeddings."""

from pathlib import Path
import time

import numpy as np

from .encoders import validate_vectors
from .io import digest, file_digest, file_lock, read_json, write_json


def vector_cache_key(data_manifest, spec, role):
    adapter = {key: value for key, value in spec.items() if key != "snapshot"}
    return digest({"release": data_manifest["release_hash"], "model": adapter, "role": role})


class VectorStore:
    def __init__(self, path, expected_key=None):
        self.path = Path(path)
        self.manifest = read_json(self.path / "manifest.json")
        if expected_key is not None and expected_key != self.manifest["cache_key"]:
            raise ValueError("Vector cache key mismatch")
        self.shards = []
        for shard in self.manifest["shards"]:
            file = self.path / shard["path"]
            if file_digest(file) != shard["sha256"]:
                raise ValueError("Vector shard checksum mismatch")
            array = np.load(file, mmap_mode="r", allow_pickle=False)
            if array.shape != (shard["end"] - shard["start"], self.manifest["dim"]):
                raise ValueError("Vector shape mismatch")
            self.shards.append((shard["start"], shard["end"], array))

    def get_rows(self, rows):
        rows = np.asarray(rows, dtype=np.int64)
        if np.any(rows < 0) or np.any(rows >= self.manifest["rows"]):
            raise IndexError("Vector row outside cache")
        result = np.empty((len(rows), self.manifest["dim"]), dtype=np.float32)
        for start, end, array in self.shards:
            mask = (rows >= start) & (rows < end)
            result[mask] = array[rows[mask] - start]
        return result

    def iter_batches(self, batch_size=4096):
        for start, end, array in self.shards:
            for local in range(0, end - start, batch_size):
                yield start + local, array[local:local + batch_size]


def encode_corpus(data, encoder, output, cache_key, shard_bytes=1 << 30):
    output = Path(output)
    with file_lock(output.with_suffix(".lock")):
        if (output / "manifest.json").exists():
            return VectorStore(output, cache_key)
        output.mkdir(parents=True, exist_ok=True)
        n, dim = len(data), encoder.spec["dim"]
        shard_rows = max(1, shard_bytes // (4 * dim))
        shards = []
        for start in range(0, n, shard_rows):
            end = min(n, start + shard_rows)
            path = output / f"vectors-{start:09d}.npy"
            part = path.with_suffix(".part.npy")
            array = np.lib.format.open_memmap(part, mode="w+", dtype=np.float32, shape=(end - start, dim))
            for offset in range(start, end, encoder.batch_size):
                rows = list(range(offset, min(end, offset + encoder.batch_size)))
                documents = data.get_documents(rows)
                array[offset - start:offset - start + len(rows)] = encoder.encode_documents([d.text for d in documents])
            array.flush()
            del array
            part.replace(path)
            shards.append({"path": path.name, "start": start, "end": end, "sha256": file_digest(path)})
        write_json(output / "manifest.json", {"cache_key": cache_key, "rows": n, "dim": dim,
                                              "dtype": "float32", "shards": shards,
                                              "encoder_cost": encoder.cost})
        return VectorStore(output, cache_key)


class PaidEmbeddingAccessor:
    """Validate the whole request before contacting a live encoder or cached source.

    The private source callback returns only requested rows. The caller never receives
    an evaluator cache handle. The optional journal records granted access before reads.
    """
    def __init__(self, source, roles, n_documents, mode="cached_access", journal=None):
        self._source = source
        self.roles = {key: set(map(int, values)) for key, values in roles.items()}
        self.n_documents = n_documents
        self.mode = mode
        self.journal = Path(journal) if journal else None
        self.paid = set()
        self.order = []
        self.cache = {}
        self.pending = []
        self.cost = {"requests": 0, "source_rows": 0, "lookup_seconds": 0.0,
                     "encoder_time_measurement": "source" if mode == "live_encode" else "not_measured"}
        if self.journal and self.journal.exists():
            record = read_json(self.journal)
            self.paid = set(record["paid"])
            self.order = record["order"]
            self.pending = record["pending"]

    def _persist(self):
        if self.journal:
            write_json(self.journal, {"paid": sorted(self.paid), "order": self.order,
                                      "pending": self.pending})

    def request(self, doc_rows, purpose, budget_limit):
        rows = list(map(int, doc_rows))
        if not rows:
            raise ValueError("Empty paid request")
        if purpose not in self.roles:
            raise PermissionError("Unknown access purpose")
        if any(r < 0 or r >= self.n_documents or r not in self.roles[purpose] for r in rows):
            raise PermissionError("Requested document is outside its split role")
        if len(self.paid | set(rows)) > budget_limit:
            raise PermissionError("Unique paid budget would be exceeded")
        missing = list(dict.fromkeys(r for r in rows if r not in self.cache))
        if missing:
            for row in missing:
                if row not in self.paid:
                    self.paid.add(row)
                    self.order.append(row)
            self.pending = missing
            self._persist()  # A failed/crashed read must never erase granted encoder access.
            start = time.monotonic()
            self.cost["source_rows"] += len(missing)
            try:
                result = np.asarray(self._source(missing), dtype=np.float32)
            finally:
                self.cost["lookup_seconds"] += time.monotonic() - start
            if len(result) != len(missing):
                raise ValueError("Source returned the wrong number of embeddings")
            validate_vectors(result)
            self.cache.update(zip(missing, result))
            self.pending = []
            self._persist()
        self.cost["requests"] += 1
        return np.stack([self.cache[r] for r in rows])
