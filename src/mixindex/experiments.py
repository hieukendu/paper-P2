"""Development setup, bounded tuning and a real FiQA exact vertical slice."""

from copy import deepcopy
import gzip
import json
from pathlib import Path
import time

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from .config import redacted_config
from .data.prepare import open_validated_data, validate_prepared
from .data.splits import sample_document_pools, stable_key
from .encoders import build_encoder, model_specs, resolve_model
from .evaluation import agreement_at_10, ndcg_hit_nfr
from .hf_sync import auto_sync_experiment, snapshot_source, source_files
from .index import ExactIndex
from .io import digest, file_digest, read_json, write_json
from .maps import fit_global_map
from .migration import bootstrap_migration, emit_checkpoint, restore_migration, run_migration
from .progress import update_checklist
from .runtime import cost_scope, probe_hardware, require_target_hardware
from .vectors import PaidEmbeddingAccessor


def source_hash(root):
    return digest({name: file_digest(root / name) for name in source_files(root) if name != "README.md"})


def finalize_run(run_dir, summary, cfg, root):
    snapshot_source(root, run_dir)
    locked = read_json(run_dir / "config.lock.json")
    expected = locked.get("source_hash")
    if expected and source_hash(run_dir / "source") != expected:
        summary = {**summary, "compute_status": "FAILED", "reason": "SOURCE_SNAPSHOT_MISMATCH"}
    write_json(run_dir / "summary.json", summary)
    update_checklist(root, run_dir.name, {**summary, "sync_status": "PENDING"})
    receipt = auto_sync_experiment(run_dir, cfg["sync"], root, cfg["paths"]) if cfg["sync"]["enabled"] else {"status": "PENDING"}
    update_checklist(root, run_dir.name, {**summary, "sync_status": receipt["status"],
                                        "hf_url": receipt.get("hf_url", "pending")})
    return {**summary, "run_id": run_dir.name, "sync_status": receipt["status"],
            "hf_url": receipt.get("hf_url")}


def _encode_subset(store, corpus_rows, query_texts, spec, cfg, output):
    output.mkdir(parents=True, exist_ok=True)
    meta_path = output / "manifest.json"
    key = digest({"rows": corpus_rows.tolist(), "queries": query_texts,
                  "spec": {k: v for k, v in spec.items() if k != "snapshot"}})
    if meta_path.exists():
        meta = read_json(meta_path)
        if meta["key"] != key:
            raise ValueError("Subset embedding cache key mismatch")
        for name, sha in meta["files"].items():
            if file_digest(output / name) != sha:
                raise ValueError("Subset embedding cache differs")
        return (np.load(output / "documents.npy", mmap_mode="r"),
                np.load(output / "queries.npy"), {**meta, "cache_hit": True})
    encoder = build_encoder(spec, cfg["execution"]["device"], cfg["models"]["batch_size"])
    try:
        values = np.empty((len(corpus_rows), spec["dim"]), dtype=np.float32)
        for start in range(0, len(corpus_rows), 64):
            documents = store.get_documents(corpus_rows[start:start + 64])
            values[start:start + len(documents)] = encoder.encode_documents([d.text for d in documents])
            if start % 256 == 0:
                print(f"encode {spec['dim']}d: {start + len(documents)}/{len(corpus_rows)} documents", flush=True)
        queries = encoder.encode_queries(query_texts)
        np.save(output / "documents.npy", values)
        np.save(output / "queries.npy", queries)
        meta = {"key": key, "encoder_cost": encoder.cost, "cache_hit": False, "files": {
            name: file_digest(output / name) for name in ("documents.npy", "queries.npy")}}
        write_json(meta_path, meta)
    finally:
        encoder.close()
    return values, queries, meta


def select_map_hyperparameters(train, val, cfg, seed=17):
    selections, table = {}, []
    for kind in ("op", "la", "residual_mlp"):
        candidates = []
        for lr in ([None] if kind == "op" else cfg["tuning"]["lr_grid"]):
            candidate_cfg = deepcopy(cfg["mapping"])
            if lr is not None:
                candidate_cfg["lr"] = lr
            try:
                model, record = fit_global_map(kind, train, val, candidate_cfg, seed)
                row = {"kind": kind, "lr": lr, "validation_loss": record["validation_loss"],
                       "status": "PASS", "epochs": record["epochs"]}
                candidates.append((row, model))
                table.append(row)
            except ValueError:
                table.append({"kind": kind, "lr": lr, "validation_loss": None, "status": "FAIL", "epochs": 0})
        if not candidates:
            raise ValueError(f"No finite candidate for {kind}")
        minimum = min(record["validation_loss"] for record, _ in candidates)
        ties = [(record, model) for record, model in candidates
                if record["validation_loss"] <= minimum + cfg["mapping"]["min_delta"]]
        selected = min(ties, key=lambda pair: (pair[0]["lr"] != 1e-3, pair[0]["lr"] or 0))
        selections[kind] = selected[0]
    return selections, table


def run_e1(cfg, root, development_hardware=False):
    environment = probe_hardware()
    if not development_hardware:
        require_target_hardware(cfg, environment)
    # A hardware diagnostic is a separate development run; it never certifies E0/E1/T0.
    cfg = deepcopy(cfg)
    cfg["execution"]["require_target"] = not development_hardware
    if cfg["execution"]["phase"] != "development":
        raise ValueError("E1 is a development correctness run")
    if cfg["mapping"]["kind"] != "op" or cfg["mapping"]["regional"] != "none" or cfg["calibration"]["enabled"]:
        raise ValueError("E1 requires OP/global-only with calibration disabled")
    prepared = Path(cfg["paths"]["data"]) / "processed" / cfg["dataset"]["name"]
    data_manifest = validate_prepared(prepared)
    store = open_validated_data(cfg["dataset"]["name"], cfg)
    ids = (prepared / "doc_ids.txt").read_text().splitlines()
    seed = cfg["splits"]["master_seed"]
    size = cfg["dataset"]["subset_size"]
    if size is None or size < 11 or size > len(ids):
        raise ValueError("E1 requires a fixed corpus subset of at least 11 rows")
    corpus_rows = np.array(sorted(sorted(range(len(ids)), key=lambda row: stable_key(seed, "E1-subset", ids[row]))[:size]), dtype=np.int64)
    doc_ids = [ids[row] for row in corpus_rows]
    roles = read_json(prepared / "splits/query_roles.json")["roles"]
    groups = {g["group_id"]: g for g in pq.read_table(prepared / "queries.parquet").to_pylist()}
    query_groups = sorted(roles["tune"], key=lambda gid: stable_key(seed, "E1-queries", gid))[:32]
    if not query_groups:
        raise ValueError("E1 needs independent development queries")
    query_ids = [groups[g]["representative_id"] for g in query_groups]
    query_texts = [groups[g]["text"] for g in query_groups]
    specs = {role: resolve_model(spec, cfg["paths"], root)
             for role, spec in model_specs(cfg["models"]["pair"], root).items()}
    inputs = {"data_release": data_manifest["release_hash"], "corpus_rows": corpus_rows.tolist(),
              "query_groups": query_groups,
              "model_specs": {r: {k: v for k, v in s.items() if k != "snapshot"} for r, s in specs.items()},
              "source_hash": source_hash(root), "config": redacted_config(cfg),
              "hardware_label": "development_other_hardware" if development_hardware else "A100_target"}
    run_hash = digest(inputs)
    run_id = f"E1{'-debug' if development_hardware else ''}-fiqa-{run_hash[:12]}"
    run_dir = Path(cfg["paths"]["runs"]) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    if (run_dir / "summary.json").exists():
        previous = read_json(run_dir / "summary.json")
        if previous.get("compute_status") == "COMPUTE_DONE":
            return finalize_run(run_dir, previous, cfg, root)
    write_json(run_dir / "config.lock.json", inputs)
    snapshot_source(root, run_dir)
    if source_hash(run_dir / "source") != inputs["source_hash"]:
        raise ValueError("Source changed while the initial run snapshot was being prepared")
    write_json(run_dir / "environment.json", environment)
    write_json(run_dir / "dataset_manifest.json", data_manifest)
    write_json(run_dir / "models.lock.json", {r: {k: v for k, v in s.items() if k != "snapshot"} for r, s in specs.items()})
    pools = sample_document_pools(doc_ids, cfg)
    reserved = set(pools["train"]) | set(pools["validation"])
    access_roles = {"train": pools["train"], "validation": pools["validation"],
                    "backfill": set(range(size)) - reserved}
    started = time.monotonic()
    timing = []
    summary = {"compute_status": "FAILED", "outcome": "diagnostic", "phase": "development",
               "hardware_label": inputs["hardware_label"], "official_gate": not development_hardware}
    try:
        cache_root = Path(cfg["paths"]["cache"])
        subset_hash = digest({k: v for k, v in inputs.items() if k not in {"source_hash", "config", "hardware_label"}})
        with cost_scope("old_setup_encoding", timing):
            old, old_queries, old_meta = _encode_subset(store, corpus_rows, query_texts, specs["old"], cfg,
                                                        cache_root / "vectors" / subset_hash)
        with cost_scope("evaluator_reference_encoding", timing):
            # This array belongs to evaluation. Migration only receives an authorized row callback.
            target, new_queries, new_meta = _encode_subset(store, corpus_rows, query_texts, specs["new"], cfg,
                                                           cache_root / "evaluator" / subset_hash)
        accessor = PaidEmbeddingAccessor(lambda rows: target[rows], access_roles, size,
                                           journal=run_dir / "access-journal.json")
        if accessor.paid:
            raise ValueError("Interrupted run has granted access; use a verified checkpoint to resume")
        with cost_scope("migration_bootstrap", timing):
            state = bootstrap_migration(doc_ids, pools, old, accessor, cfg)
        reference = ExactIndex(target, doc_ids, np.ones(size, dtype=bool)).search(new_queries)
        old_ranking = ExactIndex(old, doc_ids).search(old_queries)
        qrels = {qid: {} for qid in query_ids}
        document_population = set(doc_ids)
        for row in pq.read_table(prepared / "qrels.parquet").to_pylist():
            if row["split"] == "dev" and row["query_id"] in qrels and row["doc_id"] in document_population:
                qrels[row["query_id"]][row["doc_id"]] = row["grade"]
        full_ids = {qid: [doc_ids[r] for r in ranking[:10]] for qid, ranking in zip(query_ids, reference.rows)}
        metric_rows, checkpoints = [], []
        with gzip.open(run_dir / "retrieval.trec.gz", "wt") as retrieval:
            def evaluate(index, target_count):
                result = index.search(new_queries)
                arr = agreement_at_10(result.rows, reference.rows)
                rankings = {qid: [doc_ids[r] for r in ranking[:10]] for qid, ranking in zip(query_ids, result.rows)}
                metrics = ndcg_hit_nfr(rankings, qrels, full_ids)
                for row, value in zip(metrics, arr):
                    row.update(arr_at_10=float(value), accessed=target_count,
                               f_accessed=target_count / size, phase="development")
                    metric_rows.append(row)
                for qid, ranking in rankings.items():
                    for rank, did in enumerate(ranking, 1):
                        retrieval.write(f"{qid} Q0 {did} {rank} {-rank} {run_id}-{target_count}\n")
                path = emit_checkpoint(state, run_dir / "checkpoints", f"accessed-{target_count:07d}", run_hash)
                checkpoints.append(path)
                # Migration receives only the technical completion gate, never evaluator quality.
                return {"checkpoint_complete": True}
            evaluate(state.index, len(accessor.paid))
            targets = [int(np.floor(f * size)) for f in cfg["budget"]["checkpoints"]]
            with cost_scope("migration_and_evaluation", timing):
                result = run_migration(state, targets, evaluate)
        if not np.array_equal(state.index.vectors, target) or not np.array_equal(state.index.search(new_queries).rows, reference.rows):
            raise ValueError("100% true completion does not match full-new exact reference")
        resume_path = next(p for p in checkpoints if read_json(p / "checkpoint.json")["paid"] >= int(size * 0.1))
        resumed_accessor = PaidEmbeddingAccessor(lambda rows: target[rows], access_roles, size)
        resumed = restore_migration(resume_path, old, resumed_accessor, cfg, run_hash)
        run_migration(resumed, targets)
        if resumed.backfilled != state.backfilled or not np.array_equal(resumed.index.vectors, state.index.vectors):
            raise ValueError("Resumed exact trajectory differs from uninterrupted migration")
        pq.write_table(pa.Table.from_pylist(metric_rows), run_dir / "metrics.parquet")
        np.savez(run_dir / "accessed_ids.npz", corpus_rows=corpus_rows, paid=np.array(accessor.order),
                 train=pools["train"], validation=pools["validation"], backfilled=np.array(state.backfilled))
        from .io import atomic_bytes
        atomic_bytes(run_dir / "events.jsonl", "".join(json.dumps(event) + "\n" for event in result["events"]).encode())
        write_json(run_dir / "timing.json", {"records": timing + state.cost_records,
                                             "hardware_label": inputs["hardware_label"],
                                             "performance_claim": False,
                                             "embedding_cache_hits": {"old": old_meta["cache_hit"],
                                                                      "reference": new_meta["cache_hit"]},
                                             "encoder_cost_scope": "original cache construction, not current lookup",
                                             "old_encoder": old_meta["encoder_cost"],
                                             "reference_encoder": new_meta["encoder_cost"]})
        summary.update(compute_status="COMPUTE_DONE", documents=size, queries=len(query_ids),
                       completion_exact_agreement=1.0, resume_prefix="PASS", budget_isolation="PASS",
                       old_full_agreement=float(np.mean(agreement_at_10(old_ranking.rows, reference.rows))),
                       checkpoints=len(checkpoints), wall_seconds=time.monotonic() - started)
        if source_hash(root) != inputs["source_hash"]:
            summary.update(compute_status="FAILED", reason="SOURCE_CHANGED_DURING_RUN")
    except Exception as exc:
        summary.update(error_type=type(exc).__name__,
                       reason=str(exc) if isinstance(exc, ValueError) else "See local worker output")
    return finalize_run(run_dir, summary, cfg, root)
