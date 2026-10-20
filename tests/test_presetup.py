from copy import deepcopy

import numpy as np
import pytest

from mixindex.config import (freeze_tuning_profile, load_config, load_tuning_profiles,
                             tuning_policy, validate_tuning_profile)
from mixindex.experiments import select_map_hyperparameters
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
