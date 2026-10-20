"""Explicit publishing of validated processed datasets, separately from run bundles."""

from pathlib import Path
import shutil

from huggingface_hub import hf_hub_download

from ..hf_sync import (ArtifactBundle, ensure_repo, get_hf_client, prepare_bundle,
                      verify_remote_bundle)
from ..io import file_digest, file_lock, read_json, write_json
from .prepare import validate_prepared


def publish_dataset(name, cfg, root):
    # Raw upstream copies and pretrained weights never enter automatic run bundles.
    # This command is a separate, explicitly requested dataset publication.
    source = Path(cfg["paths"]["data"]) / "processed" / name
    manifest = validate_prepared(source)
    if name not in {"fiqa", "trec-covid"}:
        raise ValueError("Dataset redistribution recipe must be verified for this release before publishing")
    release = manifest["release_hash"]
    api, namespace = get_hf_client(root)
    repo_id = f"{namespace}/mixindex-data-{name}"
    receipt_path = Path(cfg["paths"]["state"]) / f"hf-dataset-{name}-{release}.json"
    with file_lock(receipt_path.with_suffix(".lock")):
        ensure_repo(api, repo_id, cfg["sync"])
        if receipt_path.exists() and read_json(receipt_path).get("status") == "VERIFIED":
            return read_json(receipt_path)
        upstream = api.dataset_info(f"BeIR/{name}")
        metadata = upstream.card_data.to_dict() if upstream.card_data else {}
        declared = metadata.get("license")
        if declared not in (["cc-by-sa-4.0"], "cc-by-sa-4.0"):
            raise ValueError("Upstream license metadata differs from the reviewed publication recipe")
        title = "FiQA" if name == "fiqa" else "TREC-COVID"
        origin = ("[FiQA-2018](https://sites.google.com/view/fiqa/)" if name == "fiqa" else
                   "[NIST TREC-COVID](https://ir.nist.gov/covidSubmit/data.html)")
        card_reference = f"https://huggingface.co/datasets/BeIR/{name}/blob/{upstream.sha}/README.md"
        payload = Path(cfg["paths"]["staging"]) / f"dataset-{name}-{release}"
        payload.mkdir(parents=True, exist_ok=True)
        selected = ["documents.jsonl", "doc_ids.txt", "queries.parquet", "qrels.parquet",
                    "splits/query_roles.json", "manifest.json"]
        for name_file in selected:
            dest = payload / name_file
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / name_file, dest)
        card = f"""---
license: cc-by-sa-4.0
language: [en]
task_categories: [text-retrieval]
configs:
  - config_name: corpus
    data_files:
      - split: corpus
        path: releases/{release}/documents.jsonl
  - config_name: queries
    data_files:
      - split: queries
        path: releases/{release}/queries.parquet
  - config_name: qrels
    data_files:
      - split: all
        path: releases/{release}/qrels.parquet
---
# Validated MixIndex {title} preparation

Derived from [BEIR {title}](https://huggingface.co/datasets/BeIR/{name}),
{origin} and the
[BEIR project](https://github.com/beir-cellar/beir).
Upstream dataset card declares CC BY-SA 4.0; see the [pinned card]({card_reference})
and original source links for dataset terms and attribution.
This preparation preserves source document IDs and ingestion order, joins title and body
with a newline when a title is present, groups queries by NFKC/casefold/whitespace,
and publishes fixed disjoint query roles with test > dev > train precedence.
The local SQLite lookup is omitted because it is reproducible from the document file.

Full validation found {manifest['counts']['documents']:,} documents and
{manifest['counts']['test_queries']:,} official test queries. All qrels join documents and queries.
Query roles: `{manifest['counts']['role_groups']}`. Missing independent train/dev queries
remain unavailable; test queries are never repurposed for scheduling or tuning.
Archive source checksum: `{manifest['source']['source_checksum']}`.
Release: `{release}`. Per-file SHA256 and original source/license links are in `manifest.json`.
These are prepared research inputs; no experiment quality or A100 performance is claimed.
"""
        # README is metadata for the repository and also included in the immutable release.
        from ..io import atomic_bytes
        atomic_bytes(payload / "README.md", card.encode())
        records = {name_file: {"bytes": (payload / name_file).stat().st_size,
                               "sha256": file_digest(payload / name_file)}
                   for name_file in selected + ["README.md"]}
        bundle = prepare_bundle(ArtifactBundle(f"data-{name}-{release[:12]}", payload,
                                  {"run_id": f"data-{name}-{release[:12]}",
                                   "compute_status": "COMPUTE_DONE", "files": records}),
                                 Path(cfg["paths"]["staging"]) / "dataset-bundles")
        ensure_repo(api, repo_id, cfg["sync"])
        prefix = f"releases/{release}"
        revision = api.upload_folder(repo_id=repo_id, repo_type="dataset", folder_path=str(bundle.path),
                                      path_in_repo=prefix, commit_message=f"Publish validated {name} {release[:12]}").oid
        parts = [{"repo_id": repo_id, "prefix": prefix, "revision": revision, "files": list(records)}]
        verify_remote_bundle(api, parts, bundle.manifest)
        marker = {"release_hash": release, "revision": revision,
                  "manifest_sha256": file_digest(bundle.path / "artifact_manifest.json")}
        write_json(payload / "COMPLETED.json", marker)
        completion_revision = api.upload_file(repo_id=repo_id, repo_type="dataset", path_in_repo=prefix + "/COMPLETED.json",
                                               path_or_fileobj=str(payload / "COMPLETED.json"),
                                               commit_message=f"Verify validated {name} release").oid
        check = hf_hub_download(repo_id, prefix + "/COMPLETED.json", repo_type="dataset",
                                 revision=completion_revision, token=api.token, force_download=True)
        if read_json(check) != marker:
            raise ValueError("Dataset completion marker failed verification")
        final_revision = api.upload_file(repo_id=repo_id, repo_type="dataset", path_in_repo="README.md",
                                         path_or_fileobj=str(payload / "README.md"),
                                         commit_message="Describe source attribution and validated input splits").oid
        root_card = hf_hub_download(repo_id, "README.md", repo_type="dataset", revision=final_revision,
                                     token=api.token, force_download=True)
        if file_digest(root_card) != file_digest(payload / "README.md"):
            raise ValueError("Published dataset card differs")
        receipt = {"status": "VERIFIED", "dataset": name, "repo_id": repo_id,
                   "release_hash": release, "payload_revision": revision,
                   "revision": final_revision, "files": records,
                   "upstream_card_revision": upstream.sha, "upstream_license": declared,
                   "hf_url": f"https://huggingface.co/datasets/{repo_id}"}
        write_json(receipt_path, receipt)
        return receipt
