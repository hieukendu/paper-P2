"""Strict configuration loading; credentials never enter run configuration."""

from copy import deepcopy
import os
from pathlib import Path

from dotenv import load_dotenv
import yaml

from .io import atomic_bytes, digest, file_lock, read_json, write_json


def project_root(start: Path | None = None) -> Path:
    start = Path(start or Path.cwd()).resolve()
    if start.is_file():
        start = start.parent
    for candidate in (start, *start.parents):
        if (candidate / "pyproject.toml").is_file():
            return candidate
    raise ValueError("No project pyproject.toml found; pass --root")


def load_runtime_env(root: Path) -> None:
    load_dotenv(Path(root) / ".env", override=False)


def _merge(base, update, prefix=""):
    if not isinstance(update, dict):
        raise ValueError(f"Expected mapping at {prefix or 'config'}")
    for key, value in update.items():
        if key not in base:
            raise ValueError(f"Unknown config key: {prefix}{key}")
        if isinstance(base[key], dict):
            _merge(base[key], value, prefix + key + ".")
        else:
            base[key] = value


def load_config(path: Path | str | None = None, overrides=None, root=None) -> dict:
    root = project_root(root)
    load_runtime_env(root)
    base_path = root / "configs/base.yaml"
    cfg = yaml.safe_load(base_path.read_text())
    if path:
        path = Path(path)
        path = path if path.is_absolute() else root / path
        if path.resolve() != base_path.resolve():
            _merge(cfg, yaml.safe_load(path.read_text()) or {})
    if overrides:
        _merge(cfg, overrides)
    validate_config(cfg)
    for key in cfg["paths"]:
        env_key = f"MIXINDEX_{key.upper()}_ROOT"
        value = os.getenv(env_key) or cfg["paths"][key]
        cfg["paths"][key] = str((root / value).resolve())
    return cfg


def validate_config(cfg) -> None:
    def require(condition, message):
        if not condition:
            raise ValueError(message)
    require(cfg["models"]["dtype"] == "float32", "Primary dtype must be float32")
    require(cfg["mapping"]["kind"] in {"op", "la", "residual_mlp"}, "Unknown map kind")
    require(cfg["mapping"]["regional"] in {"full", "diagonal", "none"}, "Unknown regional mode")
    require(cfg["search"]["backend"] in {"exact", "hnsw"}, "Unknown search backend")
    require(cfg["search"]["k"] == 10, "Primary k must be 10")
    require(cfg["search"]["candidates"] >= 11, "Candidate pool must include rank 11")
    require(cfg["search"]["ef_search"] >= cfg["search"]["candidates"], "ef must be >= L")
    require(cfg["search"]["threads"] >= 1, "threads must be positive")
    require(cfg["models"]["batch_size"] >= 1, "batch_size must be positive")
    require(cfg["execution"]["max_compute_jobs"] in {1, 2}, "max_compute_jobs must be 1 or 2")
    require(cfg["execution"]["phase"] in {"development", "official"}, "Unknown phase")
    require(cfg["execution"]["mode"] in {"cached_access", "live_encode"}, "Unknown encoder mode")
    require(cfg["sync"]["private"] is True, "Artifact repositories must remain private")
    require(0 < cfg["calibration"]["quantile"] <= 1, "Invalid residual quantile")
    for name in ("batch_fraction", "refit_fraction"):
        require(0 < cfg["scheduler"][name] <= 1, f"Invalid {name}")
    require(cfg["budget"]["checkpoints"] == sorted(set(cfg["budget"]["checkpoints"])),
            "Checkpoints must be unique and increasing")
    require(all(0 < f <= 1 for f in cfg["budget"]["checkpoints"]), "Invalid checkpoint")
    require(cfg["scheduler"]["kind"] in {"random", "greedy", "degree", "read", "uncertainty"},
            "Unknown scheduler")
    for section in cfg.values():
        require(isinstance(section, dict), "Config sections must be mappings")


def redacted_config(cfg) -> dict:
    clean = deepcopy(cfg)
    forbidden = ("token", "secret", "password", "credential")
    def check(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if any(word in key.lower() for word in forbidden) and key != "max_tokens":
                    raise ValueError("Credential-like key in config")
                check(child)
    check(clean)
    # Use portable path references in uploaded configuration, never local credential locations.
    clean["paths"] = {key: key for key in clean["paths"]}
    return clean


def config_hash(cfg) -> str:
    return digest(redacted_config(cfg))


def tuning_policy(cfg):
    return {"version": cfg["tuning"]["policy_version"],
            "lr_grid": cfg["tuning"]["lr_grid"], "search_grid": cfg["tuning"]["search_grid"],
            "map_architecture": {k: cfg["mapping"][k] for k in
                                 ("hidden", "rank", "batch_size", "max_epochs", "patience", "min_delta")},
            "calibration": cfg["calibration"], "budget": cfg["budget"],
            "seed": cfg["splits"]["master_seed"]}


def load_tuning_profiles(path):
    path = Path(path)
    if not path.exists():
        raise ValueError("TUNING_REQUIRED: no frozen tuning policy/profile exists")
    profiles = yaml.safe_load(path.read_text())
    if digest(profiles["policy"]) != profiles["policy_hash"]:
        raise ValueError("Tuning policy digest mismatch")
    for profile_hash, entry in profiles["profiles"].items():
        if digest(entry) != profile_hash:
            raise ValueError("Tuning profile digest mismatch")
    return profiles


def freeze_tuning_profile(scope, selections, input_refs, cfg, root):
    policy = tuning_policy(cfg)
    path = Path(root) / cfg["tuning"]["lock_path"]
    profile = {"scope": scope, "selections": selections, "inputs": input_refs,
               "policy_hash": digest(policy)}
    if not selections.get("correctness_pass") or not selections.get("local_restore_pass"):
        raise ValueError("Correctness and local restore must pass before freeze")
    if not selections.get("timing_ref") or not selections.get("estimate_ref"):
        raise ValueError("Measured timing and explicit forecast references are required")
    profile_hash = digest(profile)
    with file_lock(path.with_suffix(".lock")):
        document = load_tuning_profiles(path) if path.exists() else {
            "policy": policy, "policy_hash": digest(policy), "profiles": {}}
        if document["policy_hash"] != digest(policy):
            raise ValueError("Existing policy is immutable; a study revision requires a separate lock")
        document["profiles"].setdefault(profile_hash, profile)
        atomic_bytes(path, yaml.safe_dump(document, sort_keys=True).encode())
        index_path = Path(cfg["paths"]["state"]) / "tuning_manifest.json"
        index = read_json(index_path) if index_path.exists() else {}
        index[profile_hash] = {"scope": scope, "policy_hash": digest(policy),
                               "lock_path": cfg["tuning"]["lock_path"],
                               "source_run": selections["source_run"]}
        write_json(index_path, index)
    return profile_hash


def validate_tuning_profile(task, cfg, profiles):
    if task["phase"] != "official":
        return
    if task.get("profile_hash") not in profiles["profiles"]:
        raise ValueError("TUNING_REQUIRED: official execution needs the exact scoped profile")
    entry = profiles["profiles"][task["profile_hash"]]
    if entry["policy_hash"] != digest(tuning_policy(cfg)):
        raise ValueError("Official tuning policy mismatch")
    if entry["scope"] != task["tuning_scope"] or entry["inputs"] != task["input_refs"]:
        raise ValueError("Official dataset/model/split/runtime scope mismatch")
    settings = entry["selections"]
    if not settings.get("target_hardware_pass"):
        raise ValueError("Official execution requires a profile measured on target hardware")
    if cfg["search"]["backend"] == "hnsw" and settings.get("ann_status") != "PASS":
        raise ValueError("ANN_GATE_FAILED: exact tasks remain independently eligible")
    if task.get("overrides"):
        allowed = {"mapping.regional", "mapping.ridge", "scheduler.refit_fraction", "calibration.enabled",
                   "calibration.quantile", "scheduler.kind"}
        if not task.get("variant_id") or not set(task["overrides"]).issubset(allowed):
            raise ValueError("Ablation overrides need a declared variant and allowed keys")
