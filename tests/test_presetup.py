from copy import deepcopy

import numpy as np
import pytest

from mixindex.config import (freeze_tuning_profile, load_config, load_tuning_profiles,
                             tuning_policy, validate_tuning_profile)
from mixindex.experiments import (build_presetup_tasks, estimate_experiment_time,
                                  select_map_hyperparameters)
from mixindex.io import digest
from mixindex.maps import normalize


def test_bounded_lr_grid_selects_using_only_paid_validation(monkeypatch):
    import mixindex.experiments as experiments
    calls = []
    def fit(kind, train, val, cfg, seed):
        calls.append((kind, cfg["lr"], seed))
        # Tie within min_delta must prefer default 1e-3.
        return object(), {"validation_loss": 0.1 + (1e-6 if cfg["lr"] == 1e-3 else 0), "epochs": 2}
    monkeypatch.setattr(experiments, "fit_global_map", fit)
    values = normalize(np.ones((5, 3)))
    selected, table = select_map_hyperparameters((values, values), (values[:2], values[:2]), load_config())
    assert len(calls) == 5
    assert all(seed == 17 for _, _, seed in calls)
    assert selected["residual_mlp"]["lr"] == 1e-3
    assert selected["la"]["lr"] == 1e-3
    assert all(row["status"] == "PASS" for row in table)


def test_scope_profile_and_hardware_gates_and_immutable_merge(tmp_path):
    cfg = load_config()
    cfg["paths"]["state"] = str(tmp_path / "state")
    selections = {"correctness_pass": True, "local_restore_pass": True,
                  "target_hardware_pass": True, "ann_status": "PASS", "source_run": "T0.core.fixture",
                  "timing_ref": "timing.json", "estimate_ref": "estimate.json"}
    inputs = {"dataset": "fiqa", "release": "fixed", "pair": "minilm_mpnet"}
    profile_hash = freeze_tuning_profile("core", selections, inputs, cfg, tmp_path)
    path = tmp_path / cfg["tuning"]["lock_path"]
    old = deepcopy(load_tuning_profiles(path)["profiles"][profile_hash])
    freeze_tuning_profile("case.trec", selections, {**inputs, "dataset": "trec-covid"}, cfg, tmp_path)
    profiles = load_tuning_profiles(path)
    assert profiles["profiles"][profile_hash] == old
    task = {"phase": "official", "profile_hash": profile_hash, "tuning_scope": "core", "input_refs": inputs}
    validate_tuning_profile(task, cfg, profiles)
    with pytest.raises(ValueError, match="scope mismatch"):
        validate_tuning_profile({**task, "input_refs": {**inputs, "release": "different"}}, cfg, profiles)
    debug_profile = deepcopy(profiles)
    entry = debug_profile["profiles"].pop(profile_hash)
    entry["selections"]["target_hardware_pass"] = False
    debug_hash = digest(entry)
    debug_profile["profiles"][debug_hash] = entry
    with pytest.raises(ValueError, match="target hardware"):
        validate_tuning_profile({**task, "profile_hash": debug_hash}, cfg, debug_profile)
    with pytest.raises(ValueError, match="Ablation"):
        validate_tuning_profile({**task, "variant_id": "invalid", "overrides": {"budget.train_cap": 90000}}, cfg, profiles)


def test_profile_content_tampering_fails_before_admission(tmp_path):
    import yaml
    cfg = load_config()
    policy = tuning_policy(cfg)
    path = tmp_path / "lock.yaml"
    path.write_text(yaml.safe_dump({"policy": policy, "policy_hash": digest(policy), "profiles": {"bad-hash": {"scope": "core"}}}))
    with pytest.raises(ValueError, match="profile digest"):
        load_tuning_profiles(path)


def test_presetup_dag_orders_inputs_correctness_runtime_and_freeze():
    from mixindex.config import project_root
    from mixindex.queue import prepare_task
    cfg = load_config()
    cfg["sync"]["enabled"] = False
    jobs = [prepare_task(task, project_root()) for task in build_presetup_tasks("core", cfg, project_root())]
    by_experiment = {task["experiment"]: task for task in jobs}
    assert set(by_experiment) == {"DATA_PREP", "MODEL_DOWNLOAD", "MODEL_SMOKE", "E0", "E1",
                                   "CORE_SMOKE", "RUNTIME_PROBE", "T0"}
    for task in jobs:
        resolved = load_config(task["config"], task["config_overrides"])
        assert resolved["sync"]["enabled"] is False
        assert resolved["execution"]["target_gpu"] == "H100"
    assert by_experiment["RUNTIME_PROBE"]["task_id"] in by_experiment["T0"]["depends_on"]
    assert by_experiment["MODEL_SMOKE"]["task_id"] in by_experiment["E0"]["depends_on"]
    assert by_experiment["T0"]["measurement_mode"] == "exclusive"
    assert by_experiment["T0"]["config_overrides"]["execution"]["mode"] == "live_encode"
    assert by_experiment["T0"]["config_overrides"]["dataset"]["subset_size"] is None
    assert by_experiment["E1"]["config_overrides"]["dataset"]["subset_size"] == 2000
    assert by_experiment["E1"]["config_overrides"]["mapping"]["kind"] == "op"


def test_forecast_preserves_unknown_costs_and_never_divides_by_concurrency():
    tasks = [{"task_id": "one", "experiment": "E5"}, {"task_id": "two", "experiment": "E5"},
             {"task_id": "scale", "experiment": "E4"}]
    probes = {"shared": {"encode": {"seconds": 10, "source": "encoder_probe"}},
              "per_cell": {"E5": {"seconds": 3, "source": "actual_cell"}}}
    estimate = estimate_experiment_time(tasks, probes)
    assert estimate["task_count"] == 3 and estimate["concurrency"] == 1
    assert estimate["known_seconds"] == 16 and estimate["total_seconds"] is None
    assert estimate["unmeasured"] == [{"task_id": "scale", "component": "E4", "kind": "unmeasured"}]


def test_core_presetup_freezes_real_maps_and_restores_without_reading_test_labels(tmp_path, monkeypatch):
    """Small numerical integration fixture; downloaded encoder smoke is a separate gate."""
    import pyarrow as pa
    import pyarrow.parquet as pq
    import mixindex.encoders as encoders
    import mixindex.experiments as experiments
    from mixindex.data.store import build_document_store
    from mixindex.io import read_json, write_json
    cfg = load_config()
    cfg["paths"] = {key: str(tmp_path / key) for key in cfg["paths"]}
    cfg["sync"]["enabled"] = False
    cfg["execution"]["device"] = "cpu"
    cfg["mapping"].update(max_epochs=2, hidden=8, rank=2, min_region_pairs=2)
    cfg["tuning"].update(repeats=1, thread_grid=[1], search_grid=[[50, 200]])
    prepared = tmp_path / "data/processed/fiqa"
    build_document_store([(f"d{i:03d}", "", f"document{i}") for i in range(80)], prepared)
    roles = {"cal_fit": ["fit1", "fit2"], "cal_check": ["check1", "check2"],
             "tune": ["tune1", "tune2"], "eval": ["forbidden_test"], "schedule": []}
    groups = [{"group_id": qid, "text": qid} for values in roles.values() for qid in values]
    pq.write_table(pa.Table.from_pylist(groups), prepared / "queries.parquet")
    write_json(prepared / "splits/query_roles.json", {"roles": roles})
    manifest = {"release_hash": "fixture", "split_hash": digest(roles)}
    write_json(prepared / "manifest.json", manifest)
    environment = {"hardware": {"devices": [{"name": "H100", "vram_total_bytes": 80 << 30,
                                             "compute_capability": [9, 0]}],
                                "cpu_cores": 4, "ram_limit_bytes": 32 << 30},
                   "packages": {}, "torch_cuda": None, "hnsw_build": None}
    monkeypatch.setattr(experiments, "probe_hardware", lambda: environment)
    monkeypatch.setattr(experiments, "validate_prepared", lambda path: manifest)
    specs = {role: {"repo_id": role, "dim": 8, "snapshot": "fixture", "resolved_revision": "fixed"}
             for role in ("old", "new")}
    monkeypatch.setattr(experiments, "model_specs", lambda *args: specs)
    monkeypatch.setattr(experiments, "resolve_model", lambda spec, *args: spec)
    def prerequisite(cfg, root, label, *args):
        path = tmp_path / "runs" / label
        path.mkdir(parents=True, exist_ok=True)
        if label == "RUNTIME_PROBE":
            write_json(path / "throughput_probe.json", {"run_id": label, "environment": environment,
                       "results": {role: {"selected_batch_size": 8} for role in specs}})
        return path
    monkeypatch.setattr(experiments, "_completed_prerequisite", prerequisite)
    class Encoder:
        device = "cpu"
        def __init__(self, spec, device, batch_size):
            self.spec, self.batch_size = spec, batch_size
            self.cost = {"documents": 0}
        def encode_documents(self, texts):
            self.cost["documents"] += len(texts)
            return normalize(np.stack([np.random.default_rng(int(digest(t)[:8], 16)).normal(size=8)
                                       for t in texts]))
        encode_queries = encode_documents
        def close(self):
            pass
    monkeypatch.setattr(experiments, "build_encoder", Encoder)
    monkeypatch.setattr(encoders, "build_encoder", Encoder)
    def forbidden(*args, **kwargs):
        raise AssertionError("Presetup read evaluator labels")
    monkeypatch.setattr(experiments, "ndcg_hit_nfr", forbidden)
    original_read = pq.read_table
    def guarded_read(path, *args, **kwargs):
        assert str(path).endswith("queries.parquet"), "Presetup read a test relevance table"
        return original_read(path, *args, **kwargs)
    monkeypatch.setattr(experiments.pq, "read_table", guarded_read)
    (tmp_path / "checklist.md").write_text("<!-- progress:begin -->\n<!-- progress:end -->\n")
    result = experiments.run_presetup({"root": str(tmp_path)}, {}, cfg)
    assert result["compute_status"] == "COMPUTE_DONE", result
    assert result["local_restore"] == "PASS"
    profiles = load_tuning_profiles(tmp_path / cfg["tuning"]["lock_path"])
    entry = profiles["profiles"][result["profile_hash"]]
    assert entry["inputs"]["release"] == "fixture"
    assert set(entry["selections"]["map"]) == {"op", "la", "residual_mlp"}
    run = tmp_path / "runs" / result["run_id"]
    assert read_json(run / "config.lock.json")["config"]["execution"]["mode"] == "live_encode"
    assert len(list((run / "checkpoints").glob("*/M0.safetensors"))) == 3
    assert read_json(run / "estimate.json")["total_seconds"] is None
    assert entry["selections"]["ann_status"] == "PASS"
