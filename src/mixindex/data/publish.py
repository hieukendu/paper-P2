"""Explicit publishing of validated processed datasets, separately from run bundles."""

from pathlib import Path
import hashlib
import json
import shutil

from huggingface_hub import hf_hub_download
import pyarrow as pa
import pyarrow.parquet as pq

from ..hf_sync import (ArtifactBundle, ensure_repo, get_hf_client, prepare_bundle,
                      verify_remote_bundle)
from ..io import file_digest, file_lock, read_json, write_json
from .prepare import validate_prepared
from .download import dataset_spec, verify_source_file


BEIR_PUBLICATION_RECIPES = {
    "fiqa": ("FiQA", "https://sites.google.com/view/fiqa/"),
    "trec-covid": ("TREC-COVID", "https://ir.nist.gov/covidSubmit/data.html"),
    "nq": ("Natural Questions", "https://ai.google.com/research/NaturalQuestions/"),
    "hotpotqa": ("HotpotQA", "https://hotpotqa.github.io/"),
    "fever": ("FEVER", "https://fever.ai/"),
}


SCALE_PUBLICATION_RECIPES = {
    "msmarco-docs-v1": {
        "title": "MS MARCO Document Ranking v1",
        "source_url": "https://microsoft.github.io/msmarco/Datasets.html",
        "layout": "source-order-parquet-v1",
    },
    "orcas": {
        "title": "ORCAS static query graph",
        "source_url": "https://github.com/microsoft/msmarco/blob/master/ORCAS.md",
        "layout": "normalized-group-traffic-v1",
    },
}


def verify_document_parquet(files, expected_rows, expected_source_sha256):
    """Reconstruct the canonical document JSONL digest without materializing a corpus."""
    checksum, count = hashlib.sha256(), 0
    for file in files:
        for batch in pq.ParquetFile(file).iter_batches(batch_size=10000):
            for row in batch.to_pylist():
                if row["doc_row"] != count:
                    raise ValueError("Published document row order differs")
                record = {"doc_id": row["doc_id"], "text": row["text"]}
                checksum.update((json.dumps(record, ensure_ascii=False) + "\n").encode())
                count += 1
    if count != expected_rows or checksum.hexdigest() != expected_source_sha256:
        raise ValueError("Published documents differ from canonical source checksum")
    return {"rows": count, "canonical_documents_sha256": checksum.hexdigest(), "status": "PASS"}


def stage_document_parquet(source, output, expected_rows, rows_per_file=100000, batch_rows=10000):
    """Preserve source rows in bounded Parquet files usable directly by HF datasets."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    schema = pa.schema([("doc_row", pa.int64()), ("doc_id", pa.string()), ("text", pa.string())])
    writer, records, files, count = None, [], [], 0
    temporary = None
    try:
        with Path(source).open() as stream:
            for line in stream:
                if count % rows_per_file == 0:
                    if writer is not None:
                        if records:
                            writer.write_table(pa.Table.from_pylist(records, schema=schema))
                            records.clear()
                        writer.close()
                        temporary.replace(files[-1])
                    files.append(output / f"part-{len(files):05d}.parquet")
                    temporary = files[-1].with_suffix(".parquet.part")
                    writer = pq.ParquetWriter(temporary, schema, compression="zstd")
                record = json.loads(line)
                records.append({"doc_row": count, "doc_id": record["doc_id"], "text": record["text"]})
                count += 1
                if len(records) >= batch_rows:
                    writer.write_table(pa.Table.from_pylist(records, schema=schema))
                    records.clear()
        if writer is not None:
            if records:
                writer.write_table(pa.Table.from_pylist(records, schema=schema))
            writer.close()
            writer = None
            temporary.replace(files[-1])
        if count != expected_rows:
            raise ValueError("Published document row count differs from validated source")
        verify_document_parquet(files, expected_rows, file_digest(source))
        return files
    finally:
        if writer is not None:
            writer.close()
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _copy_scale_files(source, payload, names):
    selected = []
    for name in names:
        destination = Path(payload) / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(Path(source) / name, destination)
        selected.append(name)
    return selected


def _verify_scale_sources(name, spec, manifest, root):
    """Recheck raw bytes before a scale release is uploaded."""
    raw_root = Path(root) / "data" / "raw" / name
    if name == "msmarco-docs-v1":
        verified = {}
        for filename, expected in manifest["source"]["files"].items():
            observed = verify_source_file(raw_root / filename)
            if observed["bytes"] != expected["bytes"] or observed["sha256"] != expected["sha256"]:
                raise ValueError(f"Raw MS MARCO source differs from validated manifest: {filename}")
            verified[filename] = observed
        return verified
    filename = manifest["source"]["file"]
    observed = verify_source_file(raw_root / filename, ("md5", spec["md5"]))
    expected = manifest["source"]
    if observed["bytes"] != expected["bytes"] or observed["sha256"] != expected["sha256"]:
        raise ValueError("Raw ORCAS source differs from validated manifest")
    return observed


def stage_scale_payload(name, source, payload, manifest, source_verified, documents_repo_id=None):
    """Build a bounded, checksummed HF payload for a validated scale release."""
    source, payload = Path(source), Path(payload)
    payload.mkdir(parents=True, exist_ok=True)
    if name == "msmarco-docs-v1":
        selected = _copy_scale_files(
            source, payload,
            ["doc_ids.txt", "queries.parquet", "qrels.parquet", "splits/query_roles.json", "manifest.json"],
        )
        document_files = stage_document_parquet(
            source / "documents.jsonl", payload / "documents", manifest["counts"]["documents"]
        )
        selected.extend(str(path.relative_to(payload)) for path in document_files)
        publication = {
            "layout": SCALE_PUBLICATION_RECIPES[name]["layout"],
            "source_release_hash": manifest["release_hash"],
            "source_archive_verified": source_verified,
            "source_documents_sha256": manifest["files"]["documents.jsonl"]["sha256"],
            "document_rows": manifest["counts"]["documents"],
            "document_files": [str(path.relative_to(payload)) for path in document_files],
            "text_policy": manifest["text_policy"],
            "row_policy": manifest["row_policy"],
        }
    elif name == "orcas":
        selected = _copy_scale_files(
            source,
            payload,
            [
                "queries.parquet",
                "source_queries.parquet",
                "traffic.parquet",
                "qrels.parquet",
                "splits/query_roles.json",
                "manifest.json",
            ],
        )
        publication = {
            "layout": SCALE_PUBLICATION_RECIPES[name]["layout"],
            "source_release_hash": manifest["release_hash"],
            "source_archive_verified": source_verified,
            "documents_repo": documents_repo_id,
            "documents_release_hash": manifest["documents_release_hash"],
            "documents_rows": manifest["counts"]["documents"],
            "row_policy": manifest["row_policy"],
        }
    else:
        raise ValueError(f"No scale publication recipe for {name}")
    write_json(payload / "publication.json", publication)
    selected.append("publication.json")
    return selected


def _scale_card(name, release, manifest, repo_id, documents_repo_id=None):
    recipe = SCALE_PUBLICATION_RECIPES[name]
    if name == "msmarco-docs-v1":
        data_files = f"""configs:
  - config_name: corpus
    data_files:
      - split: corpus
        path: releases/{release}/documents/*.parquet
  - config_name: queries
    data_files:
      - split: queries
        path: releases/{release}/queries.parquet
  - config_name: qrels
    data_files:
      - split: dev
        path: releases/{release}/qrels.parquet"""
        detail = (
            f"This release contains {manifest['counts']['documents']:,} source-order documents, "
            f"{manifest['counts']['test_queries']:,} grouped judged-dev queries and "
            f"{manifest['counts']['test_qrels']:,} qrels."
        )
    else:
        data_files = f"""configs:
  - config_name: queries
    data_files:
      - split: queries
        path: releases/{release}/queries.parquet
  - config_name: source_queries
    data_files:
      - split: source_queries
        path: releases/{release}/source_queries.parquet
  - config_name: traffic
    data_files:
      - split: traffic
        path: releases/{release}/traffic.parquet
  - config_name: qrels
    data_files:
      - split: all
        path: releases/{release}/qrels.parquet"""
        detail = (
            f"This release contains {manifest['counts']['records']:,} raw ORCAS records, "
            f"{manifest['counts']['query_groups']:,} eligible query groups and "
            f"{manifest['counts']['unique_edges']:,} joined traffic edges. "
            f"Documents are referenced from `{documents_repo_id}` at the recorded release hash."
        )
    return f"""---
license: other
language: [en]
task_categories: [text-retrieval]
{data_files}
---
# Validated MixIndex {recipe['title']} preparation

Source: [{recipe['title']}]({recipe['source_url']}). This repository contains a
validated, checksummed preparation for the MixIndex experiments. It does not claim
that the source data license permits uses beyond the source terms; review the linked
source terms before redistribution or downstream use.

{detail}
Release: `{release}`. The full source manifest, per-file SHA256 values, split hash and
source archive checks are in `manifest.json` and `publication.json`.
Repository: `{repo_id}`.
"""


def publish_scale_dataset(name, cfg, root):
    """Publish a validated MS MARCO/ORCAS preparation and verify its HF round-trip."""
    if name not in SCALE_PUBLICATION_RECIPES:
        raise ValueError(f"Dataset is not a scale publication: {name}")
    source = Path(cfg["paths"]["data"]) / "processed" / name
    spec = dataset_spec(name, root)
    manifest = validate_prepared(source, spec)
    release = manifest["release_hash"]
    api, namespace = get_hf_client(root)
    repo_id = f"{namespace}/mixindex-data-{name}"
    documents_repo_id = f"{namespace}/mixindex-data-msmarco-docs-v1"
    receipt_path = Path(cfg["paths"]["state"]) / f"hf-dataset-{name}-{release}.json"
    with file_lock(receipt_path.with_suffix(".lock")):
        ensure_repo(api, repo_id, cfg["sync"])
        if receipt_path.exists() and read_json(receipt_path).get("status") == "VERIFIED":
            return read_json(receipt_path)
        source_verified = _verify_scale_sources(name, spec, manifest, root)
        payload = Path(cfg["paths"]["staging"]) / f"dataset-{name}-{release}"
        selected = stage_scale_payload(
            name, source, payload, manifest, source_verified,
            documents_repo_id if name == "orcas" else None,
        )
        from ..io import atomic_bytes
        atomic_bytes(
            payload / "README.md",
            _scale_card(name, release, manifest, repo_id,
                        documents_repo_id if name == "orcas" else None).encode(),
        )
        selected.append("README.md")
        records = {
            filename: {"bytes": (payload / filename).stat().st_size,
                       "sha256": file_digest(payload / filename)}
            for filename in selected
        }
        bundle = prepare_bundle(
            ArtifactBundle(
                f"data-{name}-{release[:12]}",
                payload,
                {"run_id": f"data-{name}-{release[:12]}",
                 "compute_status": "COMPUTE_DONE", "files": records},
            ),
            Path(cfg["paths"]["staging"]) / "dataset-bundles",
        )
        prefix = f"releases/{release}"
        revision = api.upload_folder(
            repo_id=repo_id,
            repo_type="dataset",
            folder_path=str(bundle.path),
            path_in_repo=prefix,
            commit_message=f"Publish validated {name} {release[:12]}",
        ).oid
        remote = [{"repo_id": repo_id, "prefix": prefix, "revision": revision,
                   "files": list(bundle.manifest["files"])}]
        verify_remote_bundle(api, remote, bundle.manifest)
        marker = {"release_hash": release, "revision": revision,
                  "manifest_sha256": file_digest(bundle.path / "artifact_manifest.json")}
        write_json(payload / "COMPLETED.json", marker)
        completion_revision = api.upload_file(
            repo_id=repo_id,
            repo_type="dataset",
            path_in_repo=prefix + "/COMPLETED.json",
            path_or_fileobj=str(payload / "COMPLETED.json"),
            commit_message=f"Verify validated {name} release",
        ).oid
        check = hf_hub_download(repo_id, prefix + "/COMPLETED.json", repo_type="dataset",
                                 revision=completion_revision, token=api.token, force_download=True)
        if read_json(check) != marker:
            raise ValueError("Scale dataset completion marker failed verification")
        final_revision = api.upload_file(
            repo_id=repo_id,
            repo_type="dataset",
            path_in_repo="README.md",
            path_or_fileobj=str(payload / "README.md"),
            commit_message="Describe validated scale input release",
        ).oid
        root_card = hf_hub_download(repo_id, "README.md", repo_type="dataset",
                                     revision=final_revision, token=api.token, force_download=True)
        if file_digest(root_card) != file_digest(payload / "README.md"):
            raise ValueError("Published scale dataset card differs")
        receipt = {
            "status": "VERIFIED", "dataset": name, "repo_id": repo_id,
            "release_hash": release, "payload_revision": revision,
            "revision": final_revision, "files": records,
            "hf_url": f"https://huggingface.co/datasets/{repo_id}",
        }
        write_json(receipt_path, receipt)
        return receipt


def publish_dataset(name, cfg, root):
    # Raw upstream copies and pretrained weights never enter automatic run bundles.
    # This command is a separate, explicitly requested dataset publication.
    if name in SCALE_PUBLICATION_RECIPES:
        return publish_scale_dataset(name, cfg, root)
    source = Path(cfg["paths"]["data"]) / "processed" / name
    if name not in BEIR_PUBLICATION_RECIPES:
        raise ValueError("Dataset redistribution recipe must be verified for this release before publishing")
    spec = dataset_spec(name, root)
    manifest = validate_prepared(source, spec)
    release = manifest["release_hash"]
    api, namespace = get_hf_client(root)
    repo_id = f"{namespace}/mixindex-data-{name}"
    receipt_path = Path(cfg["paths"]["state"]) / f"hf-dataset-{name}-{release}.json"
    with file_lock(receipt_path.with_suffix(".lock")):
        ensure_repo(api, repo_id, cfg["sync"])
        if receipt_path.exists() and read_json(receipt_path).get("status") == "VERIFIED":
            return read_json(receipt_path)
        # Existing prepared releases may predate adding the published source MD5.
        # Verify it separately; do not rewrite their immutable release manifests.
        raw = Path(cfg["paths"]["data"]) / "raw" / name / manifest["source"]["file"]
        source_verified = verify_source_file(raw, ("md5", spec["md5"]) if "md5" in spec else None)
        if source_verified["sha256"] != manifest["source"]["sha256"]:
            raise ValueError("Raw archive differs from the validated prepared release")
        upstream = api.dataset_info(f"BeIR/{name}")
        metadata = upstream.card_data.to_dict() if upstream.card_data else {}
        declared = metadata.get("license")
        if declared not in (["cc-by-sa-4.0"], "cc-by-sa-4.0"):
            raise ValueError("Upstream license metadata differs from the reviewed publication recipe")
        title, origin_url = BEIR_PUBLICATION_RECIPES[name]
        origin = f"[{title} source]({origin_url})"
        card_reference = f"https://huggingface.co/datasets/BeIR/{name}/blob/{upstream.sha}/README.md"
        payload = Path(cfg["paths"]["staging"]) / f"dataset-{name}-{release}"
        payload.mkdir(parents=True, exist_ok=True)
        selected = ["doc_ids.txt", "queries.parquet", "qrels.parquet",
                    "splits/query_roles.json", "manifest.json"]
        for name_file in selected:
            dest = payload / name_file
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / name_file, dest)
        document_files = stage_document_parquet(source / "documents.jsonl", payload / "documents",
                                                manifest["counts"]["documents"])
        selected += [str(p.relative_to(payload)) for p in document_files]
        write_json(payload / "publication.json", {"layout": "source-order-parquet-v1",
            "source_release_hash": release, "source_archive_verified": source_verified,
            "source_documents_sha256": manifest["files"]["documents.jsonl"]["sha256"],
            "document_rows": manifest["counts"]["documents"],
            "document_files": [str(p.relative_to(payload)) for p in document_files],
            "text_policy": manifest["text_policy"], "row_policy": manifest["row_policy"],
            "upstream_card_revision": upstream.sha, "upstream_license": declared})
        selected.append("publication.json")
        card = f"""---
license: cc-by-sa-4.0
language: [en]
task_categories: [text-retrieval]
configs:
  - config_name: corpus
    data_files:
      - split: corpus
        path: releases/{release}/documents/*.parquet
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
Archive source checksum: `{source_verified['source_checksum']}`.
Release: `{release}`. Per-file SHA256 and original source/license links are in `manifest.json`.
`publication.json` describes the additional Parquet serialization, row IDs and independently
verified source archive. Text and document order match the validated local document store.
These are prepared research inputs; experiment quality and hardware performance are unmeasured.
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
        parts = [{"repo_id": repo_id, "prefix": prefix, "revision": revision, "files": list(bundle.manifest["files"])}]
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
