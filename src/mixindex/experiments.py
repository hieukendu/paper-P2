"""Development setup, bounded tuning and a real FiQA exact vertical slice."""

from copy import deepcopy
from dataclasses import asdict
import gzip
import json
from pathlib import Path
import time
import os

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from .config import freeze_tuning_profile, redacted_config
from .data.prepare import open_validated_data, validate_prepared
from .data.splits import sample_document_pools, stable_key
from .encoders import build_encoder, model_specs, resolve_model
from .evaluation import agreement_at_10, ndcg_hit_nfr
from .hf_sync import auto_sync_experiment, snapshot_source, source_files
from .index import ExactIndex, select_search_config
from .io import digest, file_digest, read_json, write_json
from .maps import fit_global_map
from .migration import bootstrap_migration, emit_checkpoint, restore_migration, run_migration
from .progress import update_checklist
from .runtime import (cost_scope, probe_encoder, probe_hardware, probe_storage, probe_threads,
                      require_target_hardware, target_hardware_matches)
from .vectors import (PaidEmbeddingAccessor, encode_corpus, encode_query_pool, vector_cache_key)
from .scheduling import SchedulingTraffic


def source_hash(root):
    return digest({name: file_digest(root / name) for name in source_files(root) if name != "README.md"})


def finalize_run(run_dir, summary, cfg, root):
    snapshot_source(root, run_dir)
    locked = read_json(run_dir / "config.lock.json")
    expected = locked.get("source_hash")
    if expected and source_hash(run_dir / "source") != expected:
        summary = {**summary, "compute_status": "FAILED", "reason": "SOURCE_SNAPSHOT_MISMATCH"}
    write_json(run_dir / "summary.json", summary)
    worker_signal = os.getenv("MIXINDEX_WORKER_STATUS_PATH")
    if worker_signal:
        write_json(Path(worker_signal), {"compute_status": summary["compute_status"], "run_dir": str(run_dir)})
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


def hardware_identity(environment):
    hardware = environment["hardware"]
    return {"devices": [{k: d[k] for k in ("name", "vram_total_bytes", "compute_capability")}
                         for d in hardware["devices"]],
            "cpu_cores": hardware["cpu_cores"], "ram_limit_bytes": hardware["ram_limit_bytes"],
            "packages": environment["packages"], "torch_cuda": environment["torch_cuda"],
            "hnsw_build": environment["hnsw_build"]}


def _completed_prerequisite(cfg, root, experiment, release, pair):
    matches = []
    for path in Path(cfg["paths"]["runs"]).glob(f"{experiment}-*/summary.json"):
        summary = read_json(path)
        locked = read_json(path.parent / "config.lock.json")
        if (summary.get("compute_status") == "COMPUTE_DONE" and
                locked.get("source_hash") == source_hash(root) and
                locked.get("data_release") == release and
                locked.get("config", {}).get("models", {}).get("pair") == pair):
            matches.append(path.parent)
    if not matches:
        raise ValueError(f"PREREQUISITE_REQUIRED: run {experiment} for current source/data/model first")
    return sorted(matches)[-1]


def run_e0(cfg, root, development_hardware=False):
    """Verify real prepared inputs, model smoke, hardware and the paid-access boundary."""
    environment = probe_hardware()
    if not development_hardware:
        require_target_hardware(cfg, environment)
    name, pair = cfg["dataset"]["name"], cfg["models"]["pair"]
    prepared = Path(cfg["paths"]["data"]) / "processed" / name
    manifest = validate_prepared(prepared)
    specs = {role: resolve_model(spec, cfg["paths"], root)
             for role, spec in model_specs(pair, root).items()}
    smoke_path = Path(cfg["paths"]["state"]) / f"model-smoke-{name}-{pair}.json"
    if not smoke_path.exists():
        raise ValueError("MODEL_SMOKE_REQUIRED: run models prepare on validated data first")
    smoke = read_json(smoke_path)
    for role, spec in specs.items():
        if (smoke.get(role, {}).get("revision") != spec["resolved_revision"] or
                smoke.get(role, {}).get("smoke", {}).get("status") != "PASS"):
            raise ValueError("MODEL_SMOKE_REQUIRED: smoke must match both pinned revisions")
    locked = {"config": redacted_config(cfg), "source_hash": source_hash(root),
              "data_release": manifest["release_hash"], "hardware": hardware_identity(environment),
              "models": {role: {k: v for k, v in spec.items() if k != "snapshot"}
                         for role, spec in specs.items()}, "model_smoke_hash": file_digest(smoke_path)}
    run_dir = Path(cfg["paths"]["runs"]) / f"E0-{name}-{digest(locked)[:12]}"
    run_dir.mkdir(parents=True, exist_ok=True)
    if (run_dir / "summary.json").exists():
        return finalize_run(run_dir, read_json(run_dir / "summary.json"), cfg, root)
    write_json(run_dir / "config.lock.json", locked)
    snapshot_source(root, run_dir)
    write_json(run_dir / "environment.json", environment)
    write_json(run_dir / "dataset_manifest.json", manifest)
    write_json(run_dir / "models.lock.json", locked["models"])
    # Sentinel verifies denied access is rejected before any target source read.
    reads = []
    def sentinel(rows):
        reads.extend(rows)
        return np.repeat(np.array([[1., 0.]], dtype=np.float32), len(rows), axis=0)
    accessor = PaidEmbeddingAccessor(sentinel, {"train": {0}, "validation": {1}}, 2)
    for rows, purpose, cap in (([1], "train", 2), ([0], "train", 0)):
        try:
            accessor.request(rows, purpose, cap)
        except PermissionError:
            continue
        raise ValueError("ACCESSOR_GATE_FAILED: forbidden request was accepted")
    if reads:
        raise ValueError("ACCESSOR_GATE_FAILED: forbidden request read target data")
    accessor.request([0, 0], "train", 1)
    accessor.request([0], "train", 1)
    if accessor.paid != {0} or reads != [0]:
        raise ValueError("ACCESSOR_GATE_FAILED: repeated reads changed unique paid budget")
    storage = probe_storage(Path(cfg["paths"]["runs"]))
    write_json(run_dir / "timing.json", {"storage": storage, "performance_claim": False})
    return finalize_run(run_dir, {"compute_status": "COMPUTE_DONE", "phase": "development",
                                  "outcome": "diagnostic", "input_validation": "PASS",
                                  "accessor_isolation": "PASS", "model_smoke": "PASS",
                                  "target_hardware_pass": target_hardware_matches(cfg, environment),
                                  "official_gate": not development_hardware}, cfg, root)


def build_presetup_tasks(scope, cfg, root):
    """Explicit core preparation DAG; no official experiment is launched by setup."""
    if scope != "core":
        raise ValueError("Scale preparation requires the MS MARCO/ORCAS adapter and E3 gate")
    if scope == "core" and (cfg["dataset"]["name"], cfg["models"]["pair"]) != ("fiqa", "minilm_mpnet"):
        raise ValueError("T0.core requires FiQA and MiniLM/MPNet")
    revision = digest({"config": redacted_config(cfg), "source": source_hash(root)})[:12]
    prefix = f"T0.{scope}.{revision}"
    common = {"config": "configs/base.yaml", "phase": "development", "measurement_mode": "quality",
              "development_hardware": not cfg["execution"]["require_target"]}
    overrides = deepcopy(cfg)
    overrides["tuning"]["scope"] = scope
    overrides["execution"]["phase"] = "development"
    jobs = []
    for stage, experiment, dependencies, gpu in (
            ("data", "DATA_PREP", [], False), ("models", "MODEL_DOWNLOAD", [], False),
            ("smoke", "MODEL_SMOKE", ["data", "models"], True),
            ("E0", "E0", ["smoke"], True),
            ("E1", "E1", ["E0"], True),
            ("core-smoke", "CORE_SMOKE", ["E1"], True),
            ("runtime", "RUNTIME_PROBE", ["core-smoke"], True),
            ("freeze", "T0", ["E0", "E1", "core-smoke", "runtime"], True)):
        task = {**common, "task_id": f"{prefix}.{stage}", "experiment": experiment,
                "config_overrides": deepcopy(overrides),
                "depends_on": [f"{prefix}.{dependency}" for dependency in dependencies],
                "resources": {"gpu_device": 0 if gpu else None, "gpu_memory_gib": 2 if gpu else 0,
                              "host_ram_gib": 8 if gpu else 2, "cpu_cores": 4,
                              "disk_scratch_gib": 4, "io_heavy": not gpu}}
        if experiment in {"RUNTIME_PROBE", "T0"}:
            task["measurement_mode"] = "exclusive"
        if experiment == "T0":
            task["resources"]["cpu_cores"] = 8
            task["config_overrides"]["execution"]["mode"] = "live_encode"
        if experiment in {"E1", "CORE_SMOKE"}:
            task["config"] = ("configs/experiments/e1.yaml" if experiment == "E1" else
                              "configs/experiments/core_smoke.yaml")
            task["config_overrides"]["dataset"]["subset_size"] = 2000
            if experiment == "E1":
                task["config_overrides"]["mapping"].update(kind="op", regional="none")
                task["config_overrides"]["calibration"]["enabled"] = False
                task["config_overrides"]["scheduler"]["kind"] = "random"
            else:
                task["config_overrides"]["scheduler"]["kind"] = "greedy"
            task["config_overrides"]["search"]["backend"] = "exact"
        jobs.append(task)
    from .queue import validate_jobs
    return validate_jobs(jobs)


def estimate_experiment_time(task_specs, probes):
    """Only combine explicitly measured coefficients; unknown work stays unknown."""
    components, missing = [], []
    shared = probes.get("shared", {})
    for name, observation in shared.items():
        components.append({"component": name, "kind": "measured", **observation})
    for task in task_specs:
        key = task.get("cost_key", task["experiment"])
        coefficient = probes.get("per_cell", {}).get(key)
        if coefficient is None:
            missing.append({"task_id": task["task_id"], "component": key, "kind": "unmeasured"})
        else:
            components.append({"task_id": task["task_id"], "component": key, "kind": "estimated",
                               "seconds": coefficient["seconds"], "source": coefficient["source"]})
    known = sum(c["seconds"] for c in components)
    return {"task_count": len(task_specs), "components": components, "unmeasured": missing,
            "known_seconds": known, "total_seconds": None if missing else known,
            "concurrency": 1, "independent_timing_seeds": 1,
            "scope_limit": "No linear extrapolation of HNSW build/update or regional remap to full corpus"}


def run_presetup(task, inputs, cfg):
    """Tune on paid document pools and Q_tune; never construct a test evaluator."""
    root = Path(task["root"])
    cfg = deepcopy(cfg)
    cfg["execution"]["mode"] = "live_encode"
    scope = cfg["tuning"]["scope"]
    if scope != "core":
        raise ValueError("Only T0.core is integrated; case/scale profiles must not be certified yet")
    environment = probe_hardware()
    require_target_hardware(cfg, environment)
    dataset, pair = cfg["dataset"]["name"], cfg["models"]["pair"]
    if (dataset, pair) != ("fiqa", "minilm_mpnet") or cfg["dataset"]["subset_size"] is not None:
        raise ValueError("T0.core must use the complete validated FiQA corpus and MiniLM/MPNet")
    prepared = Path(cfg["paths"]["data"]) / "processed" / dataset
    manifest = validate_prepared(prepared)
    release = manifest["release_hash"]
    prerequisites = {label: _completed_prerequisite(cfg, root, label, release, pair)
                     for label in ("E0", "E1", "CORE_SMOKE", "RUNTIME_PROBE")}
    runtime_path = prerequisites["RUNTIME_PROBE"] / "throughput_probe.json"
    runtime = read_json(runtime_path)
    if hardware_identity(runtime["environment"]) != hardware_identity(environment):
        raise ValueError("RUNTIME_PROBE_REQUIRED: runtime hardware or dependencies changed")
    specs = {role: resolve_model(spec, cfg["paths"], root)
             for role, spec in model_specs(pair, root).items()}
    refs = {"dataset": dataset, "release": release, "split_hash": manifest["split_hash"],
            "pair": pair, "models": {role: {k: v for k, v in spec.items() if k != "snapshot"}
                                      for role, spec in specs.items()},
            "hardware": hardware_identity(environment)}
    locked = {"source_hash": source_hash(root), "config": redacted_config(cfg), "input_refs": refs,
              "data_release": release, "prerequisites": {k: p.name for k, p in prerequisites.items()},
              "runtime_probe_hash": file_digest(runtime_path)}
    run_dir = Path(cfg["paths"]["runs"]) / f"T0-core-{dataset}-{digest(locked)[:12]}"
    run_dir.mkdir(parents=True, exist_ok=True)
    if (run_dir / "summary.json").exists():
        return finalize_run(run_dir, read_json(run_dir / "summary.json"), cfg, root)
    write_json(run_dir / "config.lock.json", locked)
    write_json(run_dir / "dataset_manifest.json", manifest)
    write_json(run_dir / "environment.json", environment)
    write_json(run_dir / "models.lock.json", refs["models"])
    snapshot_source(root, run_dir)
    timing = []
    summary = {"compute_status": "FAILED", "phase": "development", "outcome": "diagnostic",
               "target_hardware_pass": target_hardware_matches(cfg, environment),
               "performance_claim": False, "exclusive": "unverified"}
    new_encoder = None
    try:
        from .data.store import DocumentStore
        store = DocumentStore(prepared)
        doc_ids = (prepared / "doc_ids.txt").read_text().splitlines()
        n = len(doc_ids)
        pools = sample_document_pools(doc_ids, cfg)
        cache = Path(cfg["paths"]["cache"])
        # Runtime probes are prerequisites to the first full old-corpus encode.
        old_encoder = build_encoder(specs["old"], cfg["execution"]["device"],
                                    runtime["results"]["old"]["selected_batch_size"])
        try:
            key = vector_cache_key(manifest, specs["old"], "old_documents")
            with cost_scope("old_corpus_encode_or_cache", timing):
                vectors = encode_corpus(store, old_encoder, cache / "vectors" / key, key)
            old = np.empty((n, specs["old"]["dim"]), dtype=np.float32)
            for start, values in vectors.iter_batches():
                old[start:start + len(values)] = values
        finally:
            old_encoder.close()
        roles = read_json(prepared / "splits/query_roles.json")["roles"]
        groups = {g["group_id"]: g for g in pq.read_table(prepared / "queries.parquet").to_pylist()}
        query_ids = [qid for role in ("cal_fit", "cal_check", "tune") for qid in roles[role]]
        if set(query_ids) & set(roles["eval"]):
            raise PermissionError("Test query entered presetup")
        query_cfg = deepcopy(cfg)
        query_cfg["models"]["batch_size"] = runtime["results"]["new"]["selected_batch_size"]
        with cost_scope("development_query_encode_or_cache", timing):
            queries, _ = encode_query_pool(query_ids, [groups[qid]["text"] for qid in query_ids],
                                           specs["new"], query_cfg,
                                           cache / "vectors/queries" / digest({"ids": query_ids, "model": specs["new"]}))
        by_query = dict(zip(query_ids, queries))
        cal_queries = {role: {qid: by_query[qid] for qid in roles[role]}
                       for role in ("cal_fit", "cal_check")}
        tune = np.stack([by_query[qid] for qid in roles["tune"]])
        new_encoder = build_encoder(specs["new"], cfg["execution"]["device"],
                                    runtime["results"]["new"]["selected_batch_size"])
        def live_source(rows):
            return new_encoder.encode_documents([doc.text for doc in store.get_documents(rows)])
        reserved = set(pools["train"]) | set(pools["validation"])
        accessor = PaidEmbeddingAccessor(live_source, {"train": pools["train"],
                     "validation": pools["validation"], "backfill": set(range(n)) - reserved}, n,
                     mode="live_encode", journal=run_dir / "access-journal.json")
        if accessor.paid:
            raise ValueError("Interrupted presetup has paid reads; inspect its checkpoint before resuming")
        cap = len(reserved) + 2 * pools["cal_cap"]
        with cost_scope("paid_train_validation_encode", timing):
            y_train = accessor.request(pools["train"], "train", cap)
            y_val = accessor.request(pools["validation"], "validation", cap)
        with cost_scope("validation_lr_grid", timing):
            selected, table = select_map_hyperparameters(
                (old[pools["train"]], y_train), (old[pools["validation"]], y_val), cfg)
        pq.write_table(pa.Table.from_pylist(table), run_dir / "selection.parquet")
        snapshots, common_calibration, bootstrap_records = {}, None, []
        restored_pass = True
        for kind in ("op", "la", "residual_mlp"):
            candidate = deepcopy(cfg)
            candidate["mapping"]["kind"] = kind
            candidate["search"]["backend"] = "exact"
            if selected[kind]["lr"] is not None:
                candidate["mapping"]["lr"] = selected[kind]["lr"]
            with cost_scope(f"bootstrap_{kind}", timing):
                state = bootstrap_migration(doc_ids, pools, old, accessor, candidate,
                                             calibration_queries=cal_queries,
                                             fixed_calibration_pools=common_calibration)
            common_calibration = state.calibration_pools
            checkpoint = emit_checkpoint(state, run_dir / "checkpoints", f"bootstrap-{kind}", digest(locked))
            restored_accessor = PaidEmbeddingAccessor(live_source, accessor.roles, n, mode="live_encode")
            restored = restore_migration(checkpoint, old, restored_accessor, candidate, digest(locked))
            check = tune[:min(8, len(tune))]
            restored_pass &= (np.array_equal(state.index.vectors, restored.index.vectors) and
                              np.array_equal(state.index.search(check).rows, restored.index.search(check).rows))
            snapshots[kind] = state.index
            bootstrap_records.append({"map_kind": kind, "calibration": asdict(state.index.calibration),
                                      "paid_documents": len(accessor.paid), "timing": state.cost_records})
            del state, restored, restored_accessor
        with cost_scope("thread_probe", timing):
            thread_probe = probe_threads(lambda threads: snapshots["residual_mlp"].search(tune[:16]),
                                         cfg["tuning"]["thread_grid"], cfg["tuning"]["repeats"])
        with cost_scope("ann_fidelity_grid", timing):
            search = select_search_config(snapshots, tune, cfg["tuning"]["search_grid"],
                                           cfg["tuning"]["fidelity_gate"], thread_probe["selected_threads"])
        write_json(run_dir / "timing.json", {"records": timing, "bootstraps": bootstrap_records,
                   "new_encoder": dict(new_encoder.cost), "old_encoder_original_cache_cost": vectors.manifest["encoder_cost"],
                   "performance_claim": False, "exclusive": "unverified", "runtime_run": runtime["run_id"]})
        estimate = estimate_experiment_time(
            [{"task_id": name, "experiment": name} for name in
             ("E2", "E3", "T0.scale", "E4", "E5.primary", "E5.continuation", "E6", "E7", "upload_verify")],
            {"shared": {r["component"]: {"seconds": r["wall_seconds"], "source": "timing.json"}
                         for r in timing}})
        write_json(run_dir / "estimate.json", estimate)
        selections = {"map": selected, "search": search, "ann_status": search["status"],
                      "runtime": {"batches": {role: runtime["results"][role]["selected_batch_size"]
                                               for role in ("old", "new")}, "threads": thread_probe},
                      "correctness_pass": True, "local_restore_pass": bool(restored_pass),
                      "target_hardware_pass": target_hardware_matches(cfg, environment),
                      "timing_ref": f"{run_dir.name}/timing.json", "estimate_ref": f"{run_dir.name}/estimate.json",
                      "source_run": run_dir.name, "lr_selection": cfg["tuning"]["policy_version"]}
        if source_hash(root) != locked["source_hash"]:
            raise ValueError("SOURCE_CHANGED_DURING_RUN")
        profile_hash = freeze_tuning_profile(scope, selections, refs, cfg, root)
        write_json(run_dir / "tuning_profile.json", {"profile_hash": profile_hash, "scope": scope,
                                                    "selections": selections, "inputs": refs})
        np.savez(run_dir / "accessed_ids.npz", train=pools["train"], validation=pools["validation"],
                 paid=np.array(accessor.order), cal_fit=common_calibration["cal_fit"]["rows"],
                 cal_check=common_calibration["cal_check"]["rows"])
        summary.update(compute_status="COMPUTE_DONE", profile_hash=profile_hash,
                       ann_status=search["status"], local_restore="PASS", documents=n,
                       paid_documents=len(accessor.paid), bootstrap=bootstrap_records)
    except Exception as exc:
        summary.update(error_type=type(exc).__name__,
                       reason=str(exc) if isinstance(exc, ValueError) else "See local worker output")
        if not (run_dir / "timing.json").exists():
            write_json(run_dir / "timing.json", {"records": timing, "performance_claim": False})
    finally:
        if new_encoder is not None:
            new_encoder.close()
    return finalize_run(run_dir, summary, cfg, root)


def run_encoder_probes(cfg, root, pair, dataset, device="cuda", development_hardware=False):
    cfg = deepcopy(cfg)
    cfg["models"]["pair"] = pair
    cfg["dataset"]["name"] = dataset
    cfg["execution"]["device"] = device
    cfg["execution"]["phase"] = "development"
    cfg["execution"]["require_target"] = not development_hardware
    environment = probe_hardware()
    if not development_hardware:
        require_target_hardware(cfg, environment)
    data_path = Path(cfg["paths"]["data"]) / "processed" / dataset
    manifest = validate_prepared(data_path)
    store = open_validated_data(dataset, cfg)
    ids = (data_path / "doc_ids.txt").read_text().splitlines()
    sample = sorted(sorted(range(len(ids)), key=lambda row: stable_key(
        cfg["splits"]["master_seed"], "encoder-runtime-probe", ids[row]))[:128])
    texts = [doc.text for doc in store.get_documents(sample)]
    specs = {role: resolve_model(spec, cfg["paths"], root) for role, spec in model_specs(pair, root).items()}
    inputs = {"source_hash": source_hash(root), "config": redacted_config(cfg),
              "data_release": manifest["release_hash"], "sample_rows": sample,
              "models": {role: {k: v for k, v in spec.items() if k != "snapshot"} for role, spec in specs.items()},
              "hardware": environment["hardware"], "target_hardware_pass": target_hardware_matches(cfg, environment)}
    # Device free bytes are observations, not a different scientific sample or batch grid.
    identity = {**inputs, "hardware": {k: v for k, v in environment["hardware"].items()
                                        if k not in {"ram_available_bytes", "devices"}}}
    identity["devices"] = [{k: v for k, v in d.items() if k != "vram_free_bytes"}
                             for d in environment["hardware"]["devices"]]
    run_id = f"RUNTIME_PROBE-{dataset}-{pair}-{digest(identity)[:12]}"
    run_dir = Path(cfg["paths"]["runs"]) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    if (run_dir / "summary.json").exists():
        previous = read_json(run_dir / "summary.json")
        if previous.get("compute_status") == "COMPUTE_DONE":
            return finalize_run(run_dir, previous, cfg, root)
    write_json(run_dir / "config.lock.json", inputs)
    write_json(run_dir / "environment.json", environment)
    write_json(run_dir / "dataset_manifest.json", manifest)
    snapshot_source(root, run_dir)
    summary = {"compute_status": "FAILED", "phase": "development", "outcome": "diagnostic",
               "official_gate": False, "performance_claim": False,
               "target_hardware_pass": target_hardware_matches(cfg, environment), "exclusive": "unverified"}
    results = {}
    try:
        for role, spec in specs.items():
            encoder = build_encoder(spec, device, cfg["models"]["batch_size"])
            try:
                results[role] = probe_encoder(
                    encoder, texts, cfg["tuning"]["batch_grid"], cfg["tuning"]["repeats"],
                    cfg["execution"]["gpu_headroom_gib"],
                    progress=lambda batch: print(f"{role} encoder: probe batch {batch}", flush=True))
            finally:
                encoder.close()
        record = {"run_id": run_id, "sample_rows": sample, "data_release": manifest["release_hash"],
                   "results": results, "environment": environment, "performance_claim": False}
        write_json(run_dir / "throughput_probe.json", record)
        from .io import file_lock
        path = Path(cfg["paths"]["state"]) / "throughput_probe.json"
        with file_lock(path.with_suffix(".lock")):
            registry = read_json(path) if path.exists() else {}
            registry[run_id] = {"run_dir": str(run_dir),
                                "probe_hash": file_digest(run_dir / "throughput_probe.json")}
            write_json(path, registry)
        summary.update(compute_status="COMPUTE_DONE", selected_batch_sizes={
            role: record["selected_batch_size"] for role, record in results.items()})
        if source_hash(root) != inputs["source_hash"]:
            summary.update(compute_status="FAILED", reason="SOURCE_CHANGED_DURING_RUN")
    except Exception as exc:
        summary.update(error_type=type(exc).__name__, reason="Encoder runtime probe failed")
    return finalize_run(run_dir, summary, cfg, root)


def run_e1(cfg, root, development_hardware=False):
    return _run_static_smoke(cfg, root, development_hardware)


def run_core_smoke(cfg, root, development_hardware=False):
    return _run_static_smoke(cfg, root, development_hardware, core=True)


def _run_static_smoke(cfg, root, development_hardware=False, core=False):
    environment = probe_hardware()
    if not development_hardware:
        require_target_hardware(cfg, environment)
    # A hardware diagnostic is a separate development run; it never certifies E0/E1/T0.
    cfg = deepcopy(cfg)
    cfg["execution"]["require_target"] = not development_hardware
    if cfg["execution"]["phase"] != "development":
        raise ValueError("E1 is a development correctness run")
    if not core and (cfg["mapping"]["kind"] != "op" or cfg["mapping"]["regional"] != "none" or cfg["calibration"]["enabled"]):
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
              "hardware_label": ("development_other_hardware" if development_hardware else
                                 f"{cfg['execution']['target_gpu']}_target")}
    development_roles = {}
    if core:
        for role in ("cal_fit", "cal_check", "schedule"):
            development_roles[role] = sorted(roles[role], key=lambda gid: stable_key(seed, f"core-{role}", gid))
        # This is a development correctness workload, not the full scheduling study.
        development_roles["schedule"] = development_roles["schedule"][:128]
        inputs["development_query_roles"] = development_roles
        inputs["diagnostic_only"] = True
    run_hash = digest(inputs)
    label = "CORE_SMOKE" if core else "E1"
    run_id = f"{label}{'-debug' if development_hardware else ''}-fiqa-{run_hash[:12]}"
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
               "hardware_label": inputs["hardware_label"], "official_gate": not development_hardware and not core}
    try:
        cache_root = Path(cfg["paths"]["cache"])
        subset_hash = digest({key: inputs[key] for key in
                              ("data_release", "corpus_rows", "query_groups", "model_specs")})
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
        cal_queries, traffic = None, None
        if core:
            extra_ids = [qid for values in development_roles.values() for qid in values]
            extra_texts = [groups[qid]["text"] for qid in extra_ids]
            extra_key = digest({"data_release": data_manifest["release_hash"], "ids": extra_ids,
                                "model": inputs["model_specs"]["new"]})
            extra_vectors, extra_meta = encode_query_pool(extra_ids, extra_texts, specs["new"], cfg,
                                                          cache_root / "vectors/queries" / extra_key)
            by_query = dict(zip(extra_ids, extra_vectors))
            cal_queries = {role: {qid: by_query[qid] for qid in development_roles[role]}
                           for role in ("cal_fit", "cal_check")}
            selected_groups = development_roles["schedule"]
            proxies = {qid: set() for qid in selected_groups}
            local_rows = {int(row): local for local, row in enumerate(corpus_rows)}
            train_labels = pq.read_table(prepared / "qrels.parquet", filters=[("split", "=", "train")],
                                         columns=["group_id", "doc_row", "grade"]).to_pylist()
            for row in train_labels:
                if row["grade"] > 0 and row["group_id"] in proxies and row["doc_row"] in local_rows:
                    proxies[row["group_id"]].add(local_rows[row["doc_row"]])
            traffic = SchedulingTraffic(tuple(selected_groups),
                                         np.stack([by_query[qid] for qid in selected_groups]),
                                         [proxies[qid] for qid in selected_groups])
            write_json(run_dir / "development_queries.json", {"roles": development_roles,
                                                               "cache_key": extra_meta["cache_key"]})
        with cost_scope("migration_bootstrap", timing):
            state = bootstrap_migration(doc_ids, pools, old, accessor, cfg,
                                         calibration_queries=cal_queries)
        reference = ExactIndex(target, doc_ids, np.ones(size, dtype=bool)).search(new_queries)
        old_ranking = ExactIndex(old, doc_ids).search(old_queries)
        qrels = {qid: {} for qid in query_ids}
        document_population = set(doc_ids)
        for row in pq.read_table(prepared / "qrels.parquet", filters=[("split", "=", "dev")]).to_pylist():
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
                result = run_migration(state, targets, evaluate, traffic=traffic)
        if not np.array_equal(state.index.vectors, target) or not np.array_equal(state.index.search(new_queries).rows, reference.rows):
            raise ValueError("100% true completion does not match full-new exact reference")
        resume_path = next(p for p in checkpoints if read_json(p / "checkpoint.json")["paid"] >= int(size * 0.1))
        resumed_accessor = PaidEmbeddingAccessor(lambda rows: target[rows], access_roles, size)
        resumed = restore_migration(resume_path, old, resumed_accessor, cfg, run_hash)
        run_migration(resumed, targets, traffic=traffic)
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
        if core:
            summary.update(calibration=asdict(state.index.calibration),
                           calibration_pairs={role: len(pool["pairs"]) for role, pool in state.calibration_pools.items()},
                           greedy_count=sum(event.get("greedy_count", 0) for event in result["events"]),
                           fallback_count=sum(event.get("fallback_count", 0) for event in result["events"]))
        if source_hash(root) != inputs["source_hash"]:
            summary.update(compute_status="FAILED", reason="SOURCE_CHANGED_DURING_RUN")
    except Exception as exc:
        summary.update(error_type=type(exc).__name__,
                       reason=str(exc) if isinstance(exc, ValueError) else "See local worker output")
    return finalize_run(run_dir, summary, cfg, root)
