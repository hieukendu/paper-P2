#!/usr/bin/env python3
"""Audit a pinned reviewer payload and perform one representative restore/load.

The script accepts repository IDs explicitly so the HF namespace is never
inferred from an old project URL.  It uses ``HF_TOKEN`` from the ignored
``.env`` (or the process environment), never prints the credential, and emits
only checksums, revisions, and artifact counts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from huggingface_hub import HfApi, hf_hub_download


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _download(api: HfApi, repo: str, path: str, revision: str) -> Path:
    return Path(hf_hub_download(repo, path, repo_type="dataset", revision=revision,
                                token=api.token, force_download=True))


def audit(marker_repo: str, marker_path: str, marker_revision: str, output: Path) -> dict:
    load_dotenv(Path(".env"), override=False)
    token = os.environ.get("HF_TOKEN")
    if not token:
        raise RuntimeError("HF_TOKEN is required for reviewer HF audit")
    api = HfApi(token=token)
    marker_file = _download(api, marker_repo, marker_path, marker_revision)
    marker = json.loads(marker_file.read_text(encoding="utf-8"))
    if not marker.get("payload_id") or not marker.get("manifest_sha256"):
        raise ValueError("Completion marker lacks payload or manifest digest")
    if not marker.get("parts"):
        raise ValueError("Completion marker has no remote parts")

    manifests = []
    verified_files = 0
    representative = None
    for part in marker["parts"]:
        repo = part["repo_id"]
        revision = part["revision"]
        prefix = part["prefix"]
        manifest_file = _download(api, repo, prefix + "/artifact_manifest.json", revision)
        if _sha256(manifest_file) != marker["manifest_sha256"]:
            raise ValueError(f"Manifest digest differs in {repo}@{revision}")
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        manifests.append(manifest)
        entries = list(api.list_repo_tree(repo, repo_type="dataset", path_in_repo=prefix,
                                          recursive=True, revision=revision, expand=True))
        metadata = {entry.path: entry for entry in entries if hasattr(entry, "size")}
        for name in part["files"]:
            record = manifest["files"][name]
            remote_name = prefix + "/" + name
            entry = metadata.get(remote_name)
            if entry is None or getattr(entry, "size", None) != record["bytes"]:
                raise ValueError(f"Remote size differs for {repo}/{prefix}/{name}")
            remote_sha = getattr(getattr(entry, "lfs", None), "sha256", None)
            if remote_sha is None and isinstance(getattr(entry, "lfs", None), dict):
                remote_sha = entry.lfs.get("sha256")
            if remote_sha is not None and remote_sha != record["sha256"]:
                raise ValueError(f"Remote SHA differs for {repo}/{prefix}/{name}")
            if representative is None and name.endswith("M0.safetensors"):
                local = _download(api, repo, prefix + "/" + name, revision)
                if _sha256(local) != record["sha256"]:
                    raise ValueError(f"Representative weight digest differs for {name}")
                from safetensors.numpy import load_file
                tensors = load_file(str(local))
                representative = {"path": name, "tensors": sorted(tensors),
                                  "bytes": record["bytes"], "sha256": record["sha256"]}
            verified_files += 1
    if any(manifest != manifests[0] for manifest in manifests[1:]):
        raise ValueError("Payload parts reference different manifests")
    result = {
        "status": "VERIFIED",
        "marker_repo": marker_repo,
        "marker_revision": marker_revision,
        "marker_path": marker_path,
        "payload_id": marker["payload_id"],
        "manifest_sha256": marker["manifest_sha256"],
        "parts": [{"repo_id": part["repo_id"], "revision": part["revision"],
                   "prefix": part["prefix"], "files": len(part["files"])}
                  for part in marker["parts"]],
        "verified_files": verified_files,
        "representative_restore_load": representative,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--marker-repo", required=True)
    parser.add_argument("--marker-path", required=True)
    parser.add_argument("--marker-revision", default="main")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(audit(args.marker_repo, args.marker_path, args.marker_revision, args.output),
                     indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
