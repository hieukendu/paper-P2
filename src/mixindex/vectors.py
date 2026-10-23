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

    def __len__(self):
        return int(self.manifest["rows"])

    @property
    def shape(self):
        return (len(self), int(self.manifest["dim"]))

    def __getitem__(self, key):
        """Expose the validated store as a bounded, array-like read view.

        Full-corpus bootstrap uses the same streaming shards as encoding.  A
        read view keeps migration/map code from materializing a second full
        vector matrix while preserving the existing row-alignment contract.
        """
        if isinstance(key, (int, np.integer)):
            row = int(key)
            if row < 0:
                row += len(self)
            return self.get_rows([row])[0]
        if isinstance(key, slice):
            rows = np.arange(*key.indices(len(self)), dtype=np.int64)
        else:
            rows = np.asarray(key, dtype=np.int64)
            if rows.ndim == 0:
                rows = rows.reshape(1)
        return self.get_rows(rows)

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


class RowSubsetVectorStore:
    """Read-only local-row view over an immutable validated vector store."""

    def __init__(self, base, rows):
        self.base = base
        self.rows = tuple(int(row) for row in rows)
        if any(row < 0 or row >= len(base) for row in self.rows):
            raise ValueError("Vector subset row is outside the validated store")
        if len(set(self.rows)) != len(self.rows):
            raise ValueError("Vector subset rows must be unique")
        self.manifest = {"rows": len(self.rows), "dim": base.manifest["dim"],
                         "dtype": base.manifest.get("dtype", "float32"),
                         "cache_key": base.manifest["cache_key"]}

    def __len__(self):
        return len(self.rows)

    @property
    def shape(self):
        return (len(self), int(self.manifest["dim"]))

    def get_rows(self, rows):
        rows = np.asarray(rows, dtype=np.int64)
        if np.any(rows < 0) or np.any(rows >= len(self)):
            raise IndexError("Vector subset row outside cache")
        return self.base.get_rows(np.asarray(self.rows, dtype=np.int64)[rows])

    def __getitem__(self, key):
        if isinstance(key, (int, np.integer)):
            row = int(key)
            if row < 0:
                row += len(self)
            return self.get_rows([row])[0]
        if isinstance(key, slice):
            rows = np.arange(*key.indices(len(self)), dtype=np.int64)
        else:
            rows = np.asarray(key, dtype=np.int64)
            if rows.ndim == 0:
                rows = rows.reshape(1)
        return self.get_rows(rows)

    def iter_batches(self, batch_size=4096):
        batch_size = int(batch_size)
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        for start in range(0, len(self), batch_size):
            end = min(len(self), start + batch_size)
            yield start, self.get_rows(np.arange(start, end, dtype=np.int64))


def encode_corpus(data, encoder, output, cache_key, shard_bytes=1 << 30, token_budget=None):
    output = Path(output)
    with file_lock(output.with_suffix(".lock")):
        if (output / "manifest.json").exists():
            return VectorStore(output, cache_key)
        output.mkdir(parents=True, exist_ok=True)
        n, dim = len(data), encoder.spec["dim"]
        shard_rows = max(1, shard_bytes // (4 * dim))
        progress_path = output / "progress.json"
        encoder_batch_size = max(1, int(encoder.batch_size))
        # Keep the measured forward batch immutable, but amortize tokenizer and
        # document-reader overhead over a larger host-side stream.  This is
        # independent of GPU forward batch size: the Arctic-new probe selects
        # forward batch 4, while a 256-row host stream avoids thousands of
        # unnecessarily small tokenizer calls on the full corpus.  The cap
        # bounds tokenized Python objects for the 8k-token new model.
        document_read_batch_size = min(256, max(64, encoder_batch_size * 64))
        progress_stride = max(8_192, document_read_batch_size * 32)

        # A full scale encode can outlive a worker lease.  Reuse only a
        # contiguous prefix of committed, checksummed shards from the same
        # cache key; never reuse a .part file or a shard after a gap/corruption.
        # This keeps retry data out of the completed-cache namespace while
        # avoiding an unnecessary re-encode of hours of valid work.
        shards = []
        processed = 0
        resume = None
        try:
            resume = read_json(progress_path)
        except (FileNotFoundError, ValueError):
            resume = None
        if (isinstance(resume, dict)
                and resume.get("cache_key") == cache_key
                and int(resume.get("rows_total", -1)) == n
                and int(resume.get("dim", dim)) == dim):
            for record in resume.get("shards", []):
                start = int(record.get("start", -1))
                end = int(record.get("end", -1))
                expected_end = min(n, start + shard_rows)
                path = output / str(record.get("path", ""))
                if (start != processed or end != expected_end or not path.is_file()
                        or file_digest(path) != record.get("sha256")):
                    break
                try:
                    array = np.load(path, mmap_mode="r", allow_pickle=False)
                    valid_shape = array.shape == (end - start, dim)
                    valid_dtype = array.dtype == np.dtype(np.float32)
                except (OSError, ValueError):
                    valid_shape = valid_dtype = False
                if not (valid_shape and valid_dtype):
                    break
                shards.append({"path": path.name, "start": start, "end": end,
                               "sha256": record["sha256"]})
                processed = end

        keep = {record["path"] for record in shards}
        for stale in set(output.glob("vectors-*.npy")) | set(output.glob("vectors-*.part.npy")):
            if stale.name not in keep:
                stale.unlink()

        def write_progress(status="RUNNING", rows_completed=processed):
            write_json(progress_path, {"status": status, "cache_key": cache_key,
                                       "rows_total": n, "dim": dim,
                                       "rows_completed": rows_completed,
                                       "batch_size": encoder_batch_size,
                                       "document_read_batch_size": document_read_batch_size,
                                       "shards": list(shards)})

        last_progress = processed
        write_progress()

        def open_shard(start):
            end = min(n, start + shard_rows)
            path = output / f"vectors-{start:09d}.npy"
            part = path.with_suffix(".part.npy")
            part.unlink(missing_ok=True)
            array = np.lib.format.open_memmap(part, mode="w+", dtype=np.float32,
                                              shape=(end - start, dim))
            return end, path, part, array

        def commit_shard(start, end, path, part, array):
            array.flush()
            del array
            part.replace(path)
            record = {"path": path.name, "start": start, "end": end,
                      "sha256": file_digest(path)}
            shards.append(record)
            write_progress(rows_completed=end)

        if n and processed < n:
            shard_start = processed
            shard_end, path, part, array = open_shard(shard_start)
            for documents in data.iter_batches(batch_size=document_read_batch_size):
                # The store yields from row zero.  On a retry, discard the
                # already committed prefix before encoding the next row.
                if not documents or documents[-1].row < processed:
                    continue
                if documents[0].row < processed:
                    documents = documents[processed - documents[0].row:]
                cursor = 0
                while cursor < len(documents):
                    if processed >= shard_end:
                        commit_shard(shard_start, shard_end, path, part, array)
                        shard_start = processed
                        shard_end, path, part, array = open_shard(shard_start)
                    take = min(len(documents) - cursor, shard_end - processed)
                    texts = [document.text for document in documents[cursor:cursor + take]
                             ]
                    if token_budget is not None and hasattr(encoder, "supports_token_budget"):
                        values = encoder.encode_documents(texts, token_budget=token_budget)
                    else:
                        # Keep small test/custom adapters and non-Arctic adapters
                        # source-compatible with the original corpus path.
                        values = encoder.encode_documents(texts)
                    if values.shape != (take, dim):
                        raise ValueError("Encoder returned the wrong corpus vector shape")
                    array[processed - shard_start:processed - shard_start + take] = values
                    processed += take
                    cursor += take
                    if processed == n or processed - last_progress >= progress_stride:
                        write_progress(rows_completed=processed)
                        last_progress = processed
            if processed != n:
                raise ValueError(f"Document stream ended at {processed}, expected {n}")
            commit_shard(shard_start, shard_end, path, part, array)
        else:
            processed = 0

        write_json(output / "manifest.json", {"cache_key": cache_key, "rows": n, "dim": dim,
                                              "dtype": "float32", "shards": shards,
                                              "encoder_cost": encoder.cost})
        write_progress(status="COMPLETE", rows_completed=n)
        return VectorStore(output, cache_key)


def encode_query_pool(query_ids, texts, spec, cfg, output):
    from .encoders import build_encoder
    output = Path(output)
    key = digest({"ids": list(query_ids), "texts": list(texts),
                  "model": {k: v for k, v in spec.items() if k != "snapshot"}})
    with file_lock(output.with_suffix(".lock")):
        output.mkdir(parents=True, exist_ok=True)
        marker = output / "manifest.json"
        if marker.exists():
            meta = read_json(marker)
            if meta["cache_key"] != key or file_digest(output / "queries.npy") != meta["sha256"]:
                raise ValueError("Query embedding cache mismatch")
            array = np.load(output / "queries.npy", mmap_mode="r", allow_pickle=False)
            if array.shape != (len(query_ids), spec["dim"]):
                raise ValueError("Query cache row alignment differs")
            return array, {**meta, "cache_hit": True}
        encoder = build_encoder(spec, cfg["execution"]["device"], cfg["models"]["batch_size"])
        try:
            result = np.empty((len(query_ids), spec["dim"]), dtype=np.float32)
            for start in range(0, len(query_ids), 128):
                result[start:start + 128] = encoder.encode_queries(texts[start:start + 128])
            part = output / "queries.part.npy"
            np.save(part, result)
            part.replace(output / "queries.npy")
            meta = {"cache_key": key, "query_ids": list(query_ids), "shape": list(result.shape),
                    "sha256": file_digest(output / "queries.npy"), "encoder_cost": dict(encoder.cost),
                    "cache_hit": False}
            write_json(marker, meta)
            return result, meta
        finally:
            encoder.close()


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

    def register_calibration_pools(self, pools):
        reserved = self.roles.get("train", set()) | self.roles.get("validation", set())
        seen = set(reserved)
        for role in ("cal_fit", "cal_check"):
            rows = set(map(int, pools[role]["rows"]))
            if rows & seen or any(r < 0 or r >= self.n_documents for r in rows):
                raise PermissionError("Calibration roles must be disjoint from fitting/held-out pools")
            if self.roles.get(role) and self.roles[role] != rows:
                raise PermissionError("An existing calibration role is immutable")
            seen |= rows
        for role in ("cal_fit", "cal_check"):
            self.roles[role] = set(map(int, pools[role]["rows"]))
        if "backfill" in self.roles:
            self.roles["backfill"] -= seen

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
