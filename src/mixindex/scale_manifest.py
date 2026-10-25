"""Freeze and validate the common reduced-scale input for E4--E7."""

from pathlib import Path

import numpy as np

from .data.prepare import validate_prepared
from .data.splits import stable_key
from .io import digest, file_digest, read_json, write_json


SCALE_VARIANT = "e4e567_scale_v3_50k"
SCALE_SEED = 20261020
DOCUMENT_CAP = 50_000
ORCAS_GROUP_CAP = 5_000
PARENT_SUBSET_SIZE = 100_000


def default_manifest_path(root):
    return Path(root) / "data" / "processed" / "msmarco-docs-v1" / "manifests" / (
        f"{SCALE_VARIANT}.json")


def manifest_path(cfg, root):
    configured = cfg["experiment"].get("scale_manifest_path")
    return Path(root) / configured if configured else default_manifest_path(root)


def _parent_rows(root, source_run, docs):
    run = Path(root) / "runs" / source_run
    subset_manifest_path = run / "subset_manifest.json"
    rows_path = run / "subset_rows.npy"
    if not subset_manifest_path.exists() or not rows_path.exists():
        raise ValueError("SCALE_MANIFEST_PARENT_MISSING: T0 subset artifact")
    parent = read_json(subset_manifest_path)
    rows = np.asarray(np.load(rows_path, allow_pickle=False), dtype=np.int64)
    doc_ids = (docs / "doc_ids.txt").read_text().splitlines()
    if (parent.get("seed") != SCALE_SEED or parent.get("rows") != PARENT_SUBSET_SIZE
            or len(rows) != PARENT_SUBSET_SIZE
            or parent.get("ids_sha256") != digest([
                doc_ids[int(row)] for row in rows])):
        raise ValueError("SCALE_MANIFEST_PARENT_INVALID: T0 subset hash/size mismatch")
    if len(set(rows.tolist())) != len(rows):
        raise ValueError("SCALE_MANIFEST_PARENT_INVALID: duplicate T0 rows")
    return run, parent, rows


def freeze_common_manifest(cfg, root, source_run):
    """Create the immutable common manifest before any v3 official result."""
    root = Path(root)
    docs = root / "data" / "processed" / "msmarco-docs-v1"
    orcas = root / "data" / "processed" / "orcas"
    docs_manifest = validate_prepared(docs)
    orcas_manifest = validate_prepared(orcas)
    if orcas_manifest.get("documents_release_hash") != docs_manifest["release_hash"]:
        raise ValueError("SCALE_MANIFEST_RELEASE_MISMATCH: ORCAS/MS MARCO")
    run, parent, parent_rows = _parent_rows(root, source_run, docs)
    doc_ids = (docs / "doc_ids.txt").read_text().splitlines()
    child_rows = parent_rows[:DOCUMENT_CAP]
    child_ids = [doc_ids[int(row)] for row in child_rows]
    roles = read_json(orcas / "splits" / "query_roles.json")["roles"]
    schedule_groups = list(roles.get("schedule", []))
    group_ids = sorted(schedule_groups,
                       key=lambda value: stable_key(SCALE_SEED,
                                                     f"{SCALE_VARIANT}-orcas-groups",
                                                     value))[:ORCAS_GROUP_CAP]
    if len(child_rows) != DOCUMENT_CAP or not group_ids:
        raise ValueError("SCALE_MANIFEST_EMPTY: reduced pool cannot be frozen")
    path = manifest_path(cfg, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows_path = path.with_name(path.stem + ".document_rows.npy")
    part = rows_path.with_suffix(".part.npy")
    np.save(part, child_rows)
    part.replace(rows_path)
    manifest = {
        "variant": SCALE_VARIANT,
        "seed": SCALE_SEED,
        "selection_rule": "first_50k_in_frozen_T0_scale_100k_uniform_order",
        "parent_t0_run": source_run,
        "parent_subset_manifest_sha256": file_digest(run / "subset_manifest.json"),
        "parent_subset_rows_sha256": file_digest(run / "subset_rows.npy"),
        "dataset": "msmarco-docs-v1",
        "documents_release_hash": docs_manifest["release_hash"],
        "document_rows": len(child_rows),
        "document_ids_sha256": digest(child_ids),
        "document_rows_path": rows_path.name,
        "document_rows_sha256": file_digest(rows_path),
        "orcas_release_hash": orcas_manifest["release_hash"],
        "orcas_split_hash": orcas_manifest["split_hash"],
        "orcas_selection_rule": "stable_hash_of_frozen_schedule_groups",
        "orcas_group_cap": ORCAS_GROUP_CAP,
        "orcas_group_ids": group_ids,
        "manifest_hash": None,
    }
    manifest["manifest_hash"] = digest({key: value for key, value in manifest.items()
                                         if key != "manifest_hash"})
    write_json(path, manifest)
    return manifest


def load_common_manifest(cfg, root, source_run=None, validated_releases=None):
    root = Path(root)
    path = manifest_path(cfg, root)
    if not path.exists():
        raise ValueError("SCALE_MANIFEST_REQUIRED: common v3 manifest is missing")
    manifest = read_json(path)
    expected_hash = digest({key: value for key, value in manifest.items()
                            if key != "manifest_hash"})
    if manifest.get("manifest_hash") != expected_hash:
        raise ValueError("SCALE_MANIFEST_INVALID: manifest hash mismatch")
    if manifest.get("variant") != SCALE_VARIANT:
        raise ValueError("SCALE_VARIANT_MISMATCH: expected e4e567_scale_v3_50k")
    if source_run is not None and manifest.get("parent_t0_run") != source_run:
        raise ValueError("SCALE_MANIFEST_PARENT_MISMATCH: T0 source differs")
    rows_path = path.with_name(manifest["document_rows_path"])
    if file_digest(rows_path) != manifest.get("document_rows_sha256"):
        raise ValueError("SCALE_MANIFEST_INVALID: document row hash mismatch")
    rows = np.asarray(np.load(rows_path, allow_pickle=False), dtype=np.int64)
    docs = root / "data" / "processed" / "msmarco-docs-v1"
    orcas = root / "data" / "processed" / "orcas"
    if validated_releases is None:
        docs_manifest = validate_prepared(docs)
        orcas_manifest = validate_prepared(orcas)
    else:
        docs_manifest = validated_releases["documents"]
        orcas_manifest = validated_releases["orcas"]
        if (docs_manifest.get("status") != "VALIDATED"
                or orcas_manifest.get("status") != "VALIDATED"):
            raise ValueError("SCALE_MANIFEST_INVALID: parent release attestation is not validated")
    if (len(rows) != DOCUMENT_CAP or manifest.get("document_rows") != DOCUMENT_CAP
            or manifest.get("documents_release_hash") != docs_manifest["release_hash"]
            or manifest.get("orcas_release_hash") != orcas_manifest["release_hash"]
            or manifest.get("orcas_split_hash") != orcas_manifest["split_hash"]
            or len(manifest.get("orcas_group_ids", [])) > ORCAS_GROUP_CAP):
        raise ValueError("SCALE_MANIFEST_INVALID: release or cap mismatch")
    doc_ids = (docs / "doc_ids.txt").read_text().splitlines()
    if any(row < 0 or row >= len(doc_ids) for row in rows):
        raise ValueError("SCALE_MANIFEST_INVALID: document row outside corpus")
    if manifest.get("document_ids_sha256") != digest([doc_ids[int(row)] for row in rows]):
        raise ValueError("SCALE_MANIFEST_INVALID: document IDs do not match rows")
    known_groups = set(read_json(orcas / "splits" / "query_roles.json")["roles"].get("schedule", []))
    if not set(manifest.get("orcas_group_ids", [])).issubset(known_groups):
        raise ValueError("SCALE_MANIFEST_INVALID: ORCAS group outside frozen schedule")
    return {**manifest, "path": str(path), "document_rows_array": rows,
            "document_rows_path_resolved": str(rows_path)}
