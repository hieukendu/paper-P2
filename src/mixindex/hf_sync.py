"""Immutable Hub bundles: checksum verification precedes completion markers."""

from dataclasses import dataclass
import inspect
import os
from pathlib import Path, PurePosixPath
import shutil
import time

import requests

from huggingface_hub import HfApi, hf_hub_download
from huggingface_hub.errors import HfHubHTTPError, RepositoryNotFoundError

from .config import load_runtime_env
from .io import digest, file_digest, file_lock, read_json, write_json


@dataclass
class ArtifactBundle:
    run_id: str
    path: Path
    manifest: dict


class SyncError(RuntimeError):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def get_hf_client(root):
    load_runtime_env(root)
    api = HfApi(token=os.getenv("HF_TOKEN") or None)
    try:
        info = api.whoami()
    except HfHubHTTPError as exc:
        code = exc.response.status_code if exc.response is not None else 0
        if code in {401, 403}:
            raise SyncError("AUTH_ERROR", "HF credentials do not authorize this operation") from None
        raise
    namespace = os.getenv("HF_NAMESPACE") or info["name"]
    if namespace != info["name"]:
        orgs = {org["name"]: org for org in info.get("orgs", [])}
        if namespace not in orgs or orgs[namespace].get("roleInOrg") not in {"admin", "write", "contributor"}:
            raise SyncError("AUTH_ERROR", "Configured HF namespace lacks verified create/write access")
    return api, namespace


def _safe_relative(name):
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name:
        raise SyncError("PATH_ERROR", "Unsafe artifact path")
    return path


def _inventory(path, names=None):
    files = sorted(path.rglob("*")) if names is None else [path / name for name in names]
    result = {}
    for file in files:
        if file.is_symlink():
            raise SyncError("PATH_ERROR", "Symlink in immutable bundle")
        if file.is_file():
            relative = str(file.relative_to(path))
            _safe_relative(relative)
            if any(p.startswith(".env") or p in {"hosts.yml", "token", "stored_tokens", ".git"}
                   for p in file.relative_to(path).parts):
                raise SyncError("PATH_ERROR", "Credentials are not bundle artifacts")
            result[relative] = {"bytes": file.stat().st_size, "sha256": file_digest(file)}
    return result


def collect_run_artifacts(run_dir, checkpoint=None):
    run_dir = Path(run_dir)
    summary = read_json(run_dir / "summary.json")
    if summary["compute_status"] == "RUNNING" and checkpoint is None:
        raise SyncError("NOT_READY", "Running outputs must be closed before bundling")
    allowed = {"config.lock.json", "summary.json", "metrics.parquet", "retrieval.trec.gz",
               "events.jsonl", "accessed_ids.npz", "timing.json", "estimate.json",
               "environment.json", "models.lock.json", "dataset_manifest.json", "selection.parquet",
               "development_queries.json", "throughput_probe.json", "tuning_profile.json"}
    names = [name for name in allowed if (run_dir / name).is_file()]
    checkpoints = run_dir / "checkpoints"
    if checkpoint is not None:
        checkpoints = checkpoints / checkpoint
    if checkpoints.exists():
        for marker in checkpoints.rglob("checkpoint.json"):
            if read_json(marker).get("complete"):
                names.extend(str(f.relative_to(run_dir)) for f in marker.parent.rglob("*") if f.is_file())
    if (run_dir / "source").exists():
        names.extend(str(f.relative_to(run_dir)) for f in (run_dir / "source").rglob("*") if f.is_file())
    files = _inventory(run_dir, sorted(set(names)))
    manifest = {"run_id": run_dir.name, "compute_status": summary["compute_status"], "files": files}
    return ArtifactBundle(run_dir.name, run_dir, manifest)


def prepare_bundle(bundle, staging_root, shard_bytes=2 << 30):
    bundle_hash = digest(bundle.manifest)
    destination = Path(staging_root) / bundle.run_id / bundle_hash
    manifest_path = destination / "artifact_manifest.json"
    if manifest_path.exists():
        manifest = read_json(manifest_path)
        for name, record in manifest["files"].items():
            if file_digest(destination / name) != record["sha256"]:
                raise SyncError("PATH_ERROR", "Immutable staging payload was changed")
        return ArtifactBundle(bundle.run_id, destination, manifest)
    destination.mkdir(parents=True, exist_ok=True)
    files, originals = {}, {}
    for name, metadata in bundle.manifest["files"].items():
        source = bundle.path / name
        if source.is_symlink() or file_digest(source) != metadata["sha256"]:
            raise SyncError("PATH_ERROR", "Source changed after collection")
        if metadata["bytes"] <= shard_bytes:
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)  # Copy: live writers must not mutate a hard-linked bundle.
            files[name] = metadata
        else:
            parts = []
            with source.open("rb") as f:
                for i in range((metadata["bytes"] + shard_bytes - 1) // shard_bytes):
                    part_name = f"{name}.part-{i:05d}"
                    part = destination / part_name
                    part.parent.mkdir(parents=True, exist_ok=True)
                    remaining = min(shard_bytes, metadata["bytes"] - i * shard_bytes)
                    with part.open("wb") as out:
                        while remaining:
                            block = f.read(min(8 << 20, remaining))
                            if not block:
                                raise SyncError("PATH_ERROR", "Truncated artifact during sharding")
                            out.write(block)
                            remaining -= len(block)
                    files[part_name] = {"bytes": part.stat().st_size, "sha256": file_digest(part)}
                    parts.append(part_name)
            originals[name] = {**metadata, "parts": parts}
    manifest = {**bundle.manifest, "files": files, "originals": originals, "payload_id": bundle_hash}
    write_json(manifest_path, manifest)
    return ArtifactBundle(bundle.run_id, destination, manifest)


def choose_upload_repo(bundle, registry, cfg, namespace):
    payload_id = bundle.manifest["payload_id"]
    if payload_id in registry.get("bundles", {}):
        return registry["bundles"][payload_id]["destinations"]
    repos = registry.setdefault("repos", [])
    destinations = []
    file_limit = cfg["repo_target_files"]
    byte_limit = int(cfg["repo_target_gib"] * (1 << 30))
    if file_limit < 3 or byte_limit < 1:
        raise SyncError("CONFIG_ERROR", "Invalid bundle capacity policy")
    for name, metadata in bundle.manifest["files"].items():
        if metadata["bytes"] > byte_limit:
            raise SyncError("CONFIG_ERROR", "Shard exceeds repository organization policy")
        if not repos or repos[-1]["bytes"] + metadata["bytes"] > byte_limit or repos[-1]["files"] >= file_limit - 2:
            repos.append({"repo_id": f"{namespace}/{cfg['repo_prefix']}-{len(repos) + 1:03d}",
                          "bytes": 0, "files": 0})
        repo = repos[-1]
        repo["bytes"] += metadata["bytes"]
        repo["files"] += 1
        dest = next((d for d in destinations if d["repo_id"] == repo["repo_id"]), None)
        if dest is None:
            dest = {"repo_id": repo["repo_id"], "prefix": f"runs/{bundle.run_id}/{payload_id}", "files": []}
            destinations.append(dest)
        dest["files"].append(name)
    registry.setdefault("bundles", {})[payload_id] = {"destinations": destinations}
    return destinations


def ensure_repo(api, repo_id, cfg):
    try:
        info = api.repo_info(repo_id, repo_type="dataset")
    except RepositoryNotFoundError:
        # SDK compatibility is resolved from the pinned API signature, not guessed on failures.
        private = cfg["private"]
        visibility = ({"private": private} if "private" in inspect.signature(api.create_repo).parameters
                      else {"visibility": "private" if private else "public"})
        api.create_repo(repo_id, repo_type="dataset", exist_ok=False, **visibility)
        api.upload_file(repo_id=repo_id, repo_type="dataset", path_in_repo=".mixindex.json",
                        path_or_fileobj=b'{"project":"mixindex","format":1}\n',
                        commit_message="Initialize MixIndex artifact store")
        info = api.repo_info(repo_id, repo_type="dataset")
    if info.private != cfg["private"]:
        raise SyncError("CONFIG_ERROR", "Existing repository visibility differs from sync.private")
    marker = hf_hub_download(repo_id, ".mixindex.json", repo_type="dataset", token=api.token,
                              revision=info.sha, force_download=True)
    if read_json(marker) != {"project": "mixindex", "format": 1}:
        raise SyncError("CONFIG_ERROR", "Existing repository is not managed by this project")


def _retry(call, attempts):
    for attempt in range(attempts):
        try:
            return call()
        except HfHubHTTPError as exc:
            status = exc.response.status_code if exc.response is not None else 0
            # Account/storage quota errors may use either 402, 403 or 507.
            message = str(exc).lower()
            if status in {402, 507} or "quota" in message or "storage limit" in message:
                raise SyncError("QUOTA_ERROR", "Hub account capacity exhausted; payload kept locally") from None
            if status in {401, 403}:
                raise SyncError("AUTH_ERROR", f"Hub returned HTTP {status}") from None
            if status not in {408, 429, 500, 502, 503, 504}:
                raise SyncError("CONFIG_ERROR", f"Hub returned HTTP {status}") from None
            if attempt == attempts - 1:
                raise SyncError("RETRYABLE_ERROR", "Hub retry limit reached") from None
            retry_after = exc.response.headers.get("Retry-After", "0") if exc.response is not None else "0"
            time.sleep(min(30, max(2 ** attempt, int(retry_after) if retry_after.isdigit() else 0)))
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout, OSError):
            if attempt == attempts - 1:
                raise SyncError("RETRYABLE_ERROR", "Hub connection retry limit reached") from None
            time.sleep(2 ** attempt)


def upload_bundle(api, destinations, bundle, cfg):
    revisions = []
    for dest in destinations:
        _retry(lambda: ensure_repo(api, dest["repo_id"], cfg), cfg["retries"])
        revision = _retry(lambda: api.upload_folder(
            repo_id=dest["repo_id"], repo_type="dataset", folder_path=str(bundle.path),
            path_in_repo=dest["prefix"], allow_patterns=dest["files"] + ["artifact_manifest.json"],
            commit_message=f"Store immutable {bundle.run_id} payload"), cfg["retries"])
        revisions.append({**dest, "revision": revision.oid})
    return revisions


def verify_remote_bundle(api, receipt, manifest):
    for dest in receipt:
        records = api.list_repo_tree(dest["repo_id"], repo_type="dataset", path_in_repo=dest["prefix"],
                                     recursive=True, revision=dest["revision"], expand=True)
        metadata = {r.path: r for r in records if hasattr(r, "size")}
        for name in dest["files"]:
            expected = manifest["files"][name]
            remote_name = dest["prefix"] + "/" + name
            record = metadata.get(remote_name)
            if record is None or record.size != expected["bytes"]:
                raise SyncError("VERIFY_ERROR", "Remote file is missing or size differs")
            lfs = getattr(record, "lfs", None)
            checksum = (getattr(lfs, "sha256", None) or
                        (lfs.get("sha256") if isinstance(lfs, dict) else None))
            if checksum is None:
                local = hf_hub_download(dest["repo_id"], remote_name, repo_type="dataset",
                                         revision=dest["revision"], token=api.token, force_download=True)
                checksum = file_digest(local)
            if checksum != expected["sha256"]:
                raise SyncError("VERIFY_ERROR", "Remote SHA256 differs")
        remote_manifest = hf_hub_download(dest["repo_id"], dest["prefix"] + "/artifact_manifest.json",
                                          repo_type="dataset", revision=dest["revision"], token=api.token,
                                          force_download=True)
        if read_json(remote_manifest) != manifest:
            raise SyncError("VERIFY_ERROR", "Remote manifest differs")
    return {"status": "PAYLOAD_VERIFIED", "files": len(manifest["files"])}


def update_remote_catalog(api, registry):
    if not registry.get("repos"):
        raise SyncError("CONFIG_ERROR", "No artifact catalog repository")
    import json
    payload = (json.dumps(registry, sort_keys=True, indent=2) + "\n").encode()
    commit = api.upload_file(repo_id=registry["repos"][0]["repo_id"], repo_type="dataset",
                              path_in_repo="catalog.json", path_or_fileobj=payload,
                              commit_message="Update verified MixIndex bundle catalog")
    restored = hf_hub_download(registry["repos"][0]["repo_id"], "catalog.json", repo_type="dataset",
                               revision=commit.oid, token=api.token, force_download=True)
    if read_json(restored) != registry:
        raise SyncError("VERIFY_ERROR", "Catalog round-trip mismatch")
    return commit.oid


def auto_sync_experiment(run_dir, sync_cfg, root, paths, checkpoint=None):
    run_dir = Path(run_dir)
    receipt_path = run_dir / "sync.json"
    registry_path = Path(paths["state"]) / "hf_repos.json"
    receipt = {"status": "PENDING", "run_id": run_dir.name}
    try:
        api, namespace = get_hf_client(root)
        bundle = prepare_bundle(collect_run_artifacts(run_dir, checkpoint), paths["staging"],
                                 int(sync_cfg["artifact_shard_gib"] * (1 << 30)))
        with file_lock(registry_path.with_suffix(".lock")):
            registry = read_json(registry_path) if registry_path.exists() else {"repos": [], "bundles": {}}
            previous = registry["bundles"].get(bundle.manifest["payload_id"], {})
            if previous.get("catalog_verified") and previous.get("receipt", {}).get("status") == "VERIFIED":
                write_json(receipt_path, previous["receipt"])
                return previous["receipt"]
            destinations = choose_upload_repo(bundle, registry, sync_cfg, namespace)
            write_json(registry_path, registry)  # Persist destinations before any network mutation.
            remote = upload_bundle(api, destinations, bundle, sync_cfg)
            verify_remote_bundle(api, remote, bundle.manifest)
            marker_name = {"COMPUTE_DONE": "COMPLETED.json", "FAILED": "FAILED.json"}.get(
                bundle.manifest["compute_status"], "PARTIAL.json")
            marker = {"payload_id": bundle.manifest["payload_id"],
                      "manifest_sha256": file_digest(bundle.path / "artifact_manifest.json"),
                      "parts": remote}
            marker_local = bundle.path.parent / f"{bundle.manifest['payload_id']}-{marker_name}"
            write_json(marker_local, marker)
            first = remote[0]
            commit = api.upload_file(repo_id=first["repo_id"], repo_type="dataset",
                                      path_in_repo=first["prefix"] + "/" + marker_name,
                                      path_or_fileobj=str(marker_local), commit_message=f"Verify {bundle.run_id}")
            check = hf_hub_download(first["repo_id"], first["prefix"] + "/" + marker_name,
                                    revision=commit.oid, repo_type="dataset", token=api.token,
                                    force_download=True)
            if read_json(check) != marker:
                raise SyncError("VERIFY_ERROR", "Completion marker differs")
            receipt = {"status": "VERIFIED", "run_id": run_dir.name,
                       "payload_id": bundle.manifest["payload_id"], "parts": remote,
                       "marker": {"repo_id": first["repo_id"], "path": first["prefix"] + "/" + marker_name,
                                  "revision": commit.oid},
                       "hf_url": f"https://huggingface.co/datasets/{first['repo_id']}/tree/{commit.oid}/{first['prefix']}"}
            registry["bundles"][bundle.manifest["payload_id"]]["receipt"] = receipt
            registry.setdefault("runs", {})[bundle.run_id] = {
                "payload_id": bundle.manifest["payload_id"],
                "compute_status": bundle.manifest["compute_status"], "receipt": receipt}
            write_json(registry_path, registry)
            catalog_revision = update_remote_catalog(api, registry)
            receipt["catalog_revision"] = catalog_revision
            registry["bundles"][bundle.manifest["payload_id"]]["receipt"] = receipt
            registry["bundles"][bundle.manifest["payload_id"]]["catalog_verified"] = True
            write_json(registry_path, registry)
        write_json(receipt_path, receipt)
        return receipt
    except Exception as exc:
        receipt.update(status=getattr(exc, "status", "RETRYABLE_ERROR"), error_type=type(exc).__name__)
        if isinstance(exc, SyncError):
            receipt["reason"] = str(exc)
        # No exception message: provider exceptions may contain request headers or private URLs.
        write_json(receipt_path, receipt)
        return receipt


def restore_run(receipt, output, api=None):
    output = Path(output)
    api = api or HfApi()
    if receipt.get("status") != "VERIFIED":
        raise SyncError("VERIFY_ERROR", "Only verified bundles can be restored")
    marker_ref = receipt["marker"]
    marker_file = hf_hub_download(marker_ref["repo_id"], marker_ref["path"], repo_type="dataset",
                                  revision=marker_ref["revision"], token=api.token, force_download=True)
    marker = read_json(marker_file)
    if marker["parts"] != receipt["parts"]:
        raise SyncError("VERIFY_ERROR", "Receipt and completion marker disagree")
    output.mkdir(parents=True, exist_ok=True)
    manifest = None
    for dest in receipt["parts"]:
        path = hf_hub_download(dest["repo_id"], dest["prefix"] + "/artifact_manifest.json",
                               repo_type="dataset", revision=dest["revision"], token=api.token,
                               force_download=True)
        if file_digest(path) != marker["manifest_sha256"]:
            raise SyncError("VERIFY_ERROR", "Restore manifest digest differs")
        current = read_json(path)
        if manifest is not None and current != manifest:
            raise SyncError("VERIFY_ERROR", "Parts reference different manifests")
        manifest = current
        for name in dest["files"]:
            _safe_relative(name)
            local = hf_hub_download(dest["repo_id"], dest["prefix"] + "/" + name,
                                    repo_type="dataset", revision=dest["revision"], token=api.token)
            if file_digest(local) != manifest["files"][name]["sha256"]:
                raise SyncError("VERIFY_ERROR", "Restore artifact digest differs")
            target = output / name
            if not target.resolve().is_relative_to(output.resolve()) or target.is_symlink():
                raise SyncError("PATH_ERROR", "Restore target escapes output via a symlink")
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and file_digest(target) != manifest["files"][name]["sha256"]:
                raise SyncError("PATH_ERROR", "Restore would overwrite a different local artifact")
            if not target.exists():
                shutil.copyfile(local, target)
    for name, original in manifest.get("originals", {}).items():
        _safe_relative(name)
        target = output / name
        if not target.resolve().is_relative_to(output.resolve()) or target.is_symlink():
            raise SyncError("PATH_ERROR", "Reassembly target escapes restore output")
        if target.exists():
            if file_digest(target) != original["sha256"]:
                raise SyncError("PATH_ERROR", "Reassembly would overwrite a different artifact")
            continue
        part = target.with_suffix(target.suffix + ".restore-part")
        with part.open("wb") as dest:
            for name_part in original["parts"]:
                with (output / name_part).open("rb") as source:
                    shutil.copyfileobj(source, dest, 8 << 20)
        if file_digest(part) != original["sha256"]:
            raise SyncError("VERIFY_ERROR", "Reassembled artifact digest differs")
        part.replace(target)
    write_json(output / "artifact_manifest.json", manifest)
    return output


def source_files(root):
    root = Path(root)
    names = ["pyproject.toml", "requirements.lock.txt", "README.md", "scripts/setup.sh",
             "scripts/ci-tests.yml"]
    names += [str(p.relative_to(root)) for directory in ("src", "configs", "tests")
              for p in (root / directory).rglob("*")
              if p.is_file() and "__pycache__" not in p.parts and p.suffix in {".py", ".yaml", ".json"}
              and not str(p.relative_to(root)).startswith("configs/locked/")
              and str(p.relative_to(root)) != "configs/jobs.yaml"]
    return sorted(name for name in names if (root / name).is_file())


def snapshot_source(root, run_dir):
    root, run_dir = Path(root), Path(run_dir)
    if (run_dir / "source").exists():
        return  # A run's source snapshot is closed before compute and never overwritten.
    for name in source_files(root):
        source = root / name
        if source.is_file():
            target = run_dir / "source" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)


def sync_self_test(root, cfg):
    import numpy as np
    from safetensors.numpy import load_file, save_file
    from .config import redacted_config
    # Changing source creates a new run, preserving earlier self-test artifacts.
    source_hash = digest({str(p.relative_to(root)): file_digest(p)
                          for p in sorted((Path(root) / "src").rglob("*.py"))})[:12]
    path = Path(cfg["paths"]["runs"]) / f"hf-self-test-{source_hash}"
    path.mkdir(parents=True, exist_ok=True)
    write_json(path / "config.lock.json", redacted_config(cfg))
    checkpoint = path / "checkpoints/tiny"
    checkpoint.mkdir(parents=True, exist_ok=True)
    weights = np.arange(12, dtype=np.float32).reshape(3, 4)
    save_file({"weights": weights}, str(checkpoint / "map.safetensors"))
    np.savez(checkpoint / "ids.npz", rows=np.arange(3))
    write_json(checkpoint / "checkpoint.json", {"complete": True})
    write_json(path / "summary.json", {"compute_status": "COMPUTE_DONE", "outcome": "diagnostic"})
    snapshot_source(root, path)
    receipt = auto_sync_experiment(path, cfg["sync"], root, cfg["paths"])
    if receipt["status"] != "VERIFIED":
        return receipt
    api, _ = get_hf_client(root)
    restored = restore_run(receipt, Path(cfg["paths"]["state"]) / "self-test-restored" / path.name, api)
    if not np.array_equal(load_file(restored / "checkpoints/tiny/map.safetensors")["weights"], weights):
        raise SyncError("VERIFY_ERROR", "Restored learned state does not load correctly")
    with np.load(restored / "checkpoints/tiny/ids.npz") as data:
        if not np.array_equal(data["rows"], np.arange(3)):
            raise SyncError("VERIFY_ERROR", "Restored IDs differ")
    return {**receipt, "restore_load": "PASS"}
