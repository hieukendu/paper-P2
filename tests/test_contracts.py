"""Fixtures target scientific errors, not implementation-shaped smoke assertions."""

import itertools
import zipfile

import numpy as np
import pytest
import torch

from mixindex.calibration import Calibration, compute_radius, fit_score_calibration, fit_with_roles
from mixindex.config import load_config, redacted_config
from mixindex.data.download import extract_beir, verify_source_file
from mixindex.data.splits import build_static_splits, finalize_calibration_pools, group_queries
from mixindex.data.store import build_document_store
from mixindex.hf_sync import ArtifactBundle, SyncError, choose_upload_repo, prepare_bundle
from mixindex.index import ExactIndex, HnswIndex, SearchResult, load_index, validate_ann_snapshot
from mixindex.io import digest, file_digest
from mixindex.maps import (RegionalStatistics, choose_region_count, fit_global_map, fit_op,
                           load_map_state, normalize, save_map_state, transform_global)
from mixindex.runtime import effective_limits, require_target_hardware, target_hardware_matches
from mixindex.scheduling import build_candidate_sets, choose_batch_cap, select_greedy
from mixindex.vectors import PaidEmbeddingAccessor


torch.set_num_threads(2)


def test_config_rejects_unknown_or_inconsistent_settings():
    with pytest.raises(ValueError, match="Unknown config key"):
        load_config(overrides={"mapping": {"typo_lr": 1}})
    with pytest.raises(ValueError, match="ef"):
        load_config(overrides={"search": {"candidates": 500}})
    cfg = load_config()
    assert "HF_TOKEN" not in str(redacted_config(cfg))
    with pytest.raises(RuntimeError, match="BLOCKED_HARDWARE"):
        require_target_hardware(cfg, {"hardware": {"devices": []}})


def test_query_groups_and_priority_block_text_leakage():
    groups = group_queries([("train1", "  KIND  BANK "), ("test1", "kind bank"),
                            ("train2", "other?"), ("dev1", "tuning")])
    split = build_static_splits(groups, {"test": {"test1"}, "dev": {"dev1"}, "train": {"train1", "train2"}})
    assert split["removed_overlap_groups"]["train"] == 1
    assert len(split["roles"]["eval"]) == 1
    flattened = list(itertools.chain.from_iterable(split["roles"].values()))
    assert len(flattened) == len(set(flattened))
    with pytest.raises(ValueError, match="Conflicting"):
        group_queries([("q", "first"), ("q", "second")])


def test_calibration_document_pools_are_disjoint_and_bounded():
    result = finalize_calibration_pools({"cal_fit": [("a", 0), ("a", 1), ("a", 2), ("b", 2)],
                                         "cal_check": [("c", 1), ("c", 3), ("d", 4)]},
                                        reserved=[0], caps={"cal_fit": 1, "cal_check": 1})
    assert result["cal_fit"]["rows"] == [1]
    assert result["cal_check"]["rows"] == [3]


def test_document_lookup_preserves_requested_rows_and_duplicate_policy(tmp_path):
    store, counts = build_document_store([("b", "title", "body"), ("a", "", "text"),
                                           ("b", "title", "body")], tmp_path / "store")
    assert counts["duplicate_documents"] == 1
    docs = store.get_documents([1, 0])
    assert [d.doc_id for d in docs] == ["a", "b"]
    assert docs[1].text == "title\nbody"
    with pytest.raises(ValueError, match="Conflicting"):
        build_document_store([("d", "", "a"), ("d", "", "b")], tmp_path / "bad")


def test_archive_rejects_traversal_and_truncation(tmp_path):
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as f:
        f.writestr("../escape", "no")
    with pytest.raises(ValueError, match="Unsafe"):
        extract_beir(archive, tmp_path / "out")
    archive.write_bytes(b"not a zip")
    with pytest.raises(zipfile.BadZipFile):
        verify_source_file(archive)


def test_accessor_checks_entire_request_before_source_and_unique_union(tmp_path):
    calls = []
    def source(rows):
        calls.append(rows)
        return np.eye(4, dtype=np.float32)[rows]
    accessor = PaidEmbeddingAccessor(source, {"train": [0, 1], "validation": [2]}, 4,
                                       journal=tmp_path / "access.json")
    with pytest.raises(PermissionError):
        accessor.request([0, 2], "train", 4)
    with pytest.raises(PermissionError):
        accessor.request([0, 1], "train", 1)
    assert calls == []
    accessor.request([0, 0], "train", 1)
    accessor.request([0], "train", 1)
    assert accessor.paid == {0} and calls == [[0]]
    with pytest.raises(PermissionError):
        accessor.request([2], "validation", 1)
    accessor.request([2], "validation", 2)
    assert accessor.order == [0, 2]


def test_failed_accessor_keeps_granted_ids_on_restart(tmp_path):
    journal = tmp_path / "access.json"
    def fail(rows):
        raise OSError("interrupted encoder")
    accessor = PaidEmbeddingAccessor(fail, {"backfill": [0, 1]}, 2, journal=journal)
    with pytest.raises(OSError):
        accessor.request([0], "backfill", 1)
    assert accessor.cost["source_rows"] == 1
    restored = PaidEmbeddingAccessor(fail, {"backfill": [0, 1]}, 2, journal=journal)
    assert restored.paid == {0} and restored.pending == [0]
    with pytest.raises(PermissionError):
        restored.request([1], "backfill", 1)


@pytest.mark.parametrize("old_dim,new_dim", [(3, 3), (3, 5), (5, 3)])
def test_procrustes_known_isometry_and_roundtrip(old_dim, new_dim, tmp_path):
    rng = np.random.default_rng(7)
    x = rng.normal(size=(80, old_dim))
    if old_dim <= new_dim:
        rotation, _ = np.linalg.qr(rng.normal(size=(new_dim, new_dim)))
        y = np.pad(x, ((0, 0), (0, new_dim - old_dim))) @ rotation
    else:
        x[:, new_dim:] = 0
        rotation, _ = np.linalg.qr(rng.normal(size=(new_dim, new_dim)))
        y = x[:, :new_dim] @ rotation
    model = fit_op(x, y)
    assert np.allclose(transform_global(model, x), y, atol=1e-5)
    save_map_state(model, tmp_path / "op.safetensors")
    assert np.array_equal(transform_global(load_map_state(tmp_path / "op.safetensors"), x),
                           transform_global(model, x))


@pytest.mark.parametrize("kind", ["la", "residual_mlp"])
def test_learned_map_checkpoint_load_preserves_outputs(kind, tmp_path):
    rng = np.random.default_rng(19)
    x, y = normalize(rng.normal(size=(50, 3))), normalize(rng.normal(size=(50, 5)))
    cfg = {**load_config()["mapping"], "max_epochs": 3, "hidden": 8, "rank": 2}
    model, record = fit_global_map(kind, (x[:40], y[:40]), (x[40:], y[40:]), cfg)
    save_map_state(model, tmp_path / "map.safetensors")
    restored = load_map_state(tmp_path / "map.safetensors")
    assert record["epochs"] <= 3
    assert np.array_equal(transform_global(model, x), transform_global(restored, x))


def test_incremental_regional_ridge_matches_joint_fit_and_excludes_holdouts():
    rng = np.random.default_rng(12)
    u, y = rng.normal(size=(40, 3)), rng.normal(size=(40, 3))
    assignment = np.arange(40) % 2
    full, incremental = RegionalStatistics(3, 2), RegionalStatistics(3, 2)
    full.add_pairs(np.arange(40), u, y, assignment)
    incremental.add_pairs(np.arange(15), u[:15], y[:15], assignment)
    incremental.add_pairs(np.arange(15, 40), u[15:], y[15:], assignment)
    assert np.allclose(full.fit(), incremental.fit(), rtol=1e-7, atol=1e-9)
    with pytest.raises(ValueError, match="twice"):
        incremental.add_pairs([0], u[:1], y[:1], assignment)
    blocked = RegionalStatistics(3, 2)
    with pytest.raises(PermissionError):
        blocked.add_pairs([0], u[:1], y[:1], assignment, excluded=[0])
    assert choose_region_count(1153) == 8
    assert choose_region_count(3427) == 32
    assert choose_region_count(10000) == 64


def test_positive_calibration_and_exact_quantile_do_not_invent_radius():
    s = np.array([0.1, 0.2, 0.3])
    cal = fit_score_calibration(s, 2 * s + 0.7)
    assert cal.a == pytest.approx(2) and cal.b == pytest.approx(0.7)
    assert fit_score_calibration(s, -s).a == 1e-6
    assert fit_score_calibration([1, 1], [0, 1]).reason == "degenerate_variance"
    assert compute_radius(np.zeros(20), np.arange(20), 1, 0) == 18
    missing = fit_with_roles([], [], [], [], [], [], load_config()["calibration"])
    assert missing.radius is None and missing.a == 1


def test_exact_calibration_retrieves_outside_raw_top_k_and_breaks_chunk_ties():
    vectors = normalize(np.array([[1, 0]] * 12 + [[0, 1]], dtype=np.float32))
    ids = [str(i).zfill(2) for i in reversed(range(13))]
    fidelity = np.ones(13, dtype=bool)
    fidelity[-1] = False
    index = ExactIndex(vectors, ids, fidelity, Calibration(1, 2), chunk_rows=3)
    result = index.search([[1, 0]])
    assert result.rows[0, 0] == 12  # Calibration can bring this raw-rank-13 document to rank 1.
    assert list(index.ids[result.rows[0, 1:]]) == sorted(ids[:-1])[:10]


def test_all_mapped_positive_calibration_preserves_ranking():
    vectors = normalize(np.random.default_rng(21).normal(size=(30, 5)))
    ids = list(map(str, range(30)))
    raw = ExactIndex(vectors, ids)
    cal = ExactIndex(vectors, ids, calibration=Calibration(0.7, 0.2))
    assert np.array_equal(raw.search(vectors[:4]).rows, cal.search(vectors[:4]).rows)


def test_hnsw_same_id_save_load_and_snapshot_fidelity(tmp_path):
    vectors = normalize(np.random.default_rng(4).normal(size=(80, 12)))
    ids = [str(i) for i in range(80)]
    index = HnswIndex(vectors, ids, candidates=80)
    changed = -vectors[:2]
    index.commit_index_update([0, 1], changed, [True, True])
    exact = ExactIndex(index.vectors, ids, index.fidelity)
    gate = validate_ann_snapshot(index, exact, vectors[10:15])
    assert gate["serving_recall_at_10"] == 1
    index.save_index(tmp_path)
    restored = load_index(tmp_path)
    assert restored.graph.get_current_count() == 80
    assert restored.parameters["ef_search"] == 200
    assert np.array_equal(index.search(vectors[10:15]).rows, restored.search(vectors[10:15]).rows)


def test_failed_partial_update_cannot_keep_serving():
    vectors = normalize(np.random.default_rng(1).normal(size=(12, 4)))
    index = ExactIndex(vectors, list(map(str, range(12))))
    def fail(rows, values):
        index.vectors[rows] = values
        raise OSError("injected partial update")
    index._write_vectors = fail
    with pytest.raises(OSError):
        index.commit_index_update([0], -vectors[:1], [True])
    with pytest.raises(RuntimeError, match="FAILED_SNAPSHOT"):
        index.search(vectors[:1])


def test_rescue_band_safe_queries_and_true_exclusion():
    rows = np.array([np.arange(11)] * 3)
    scores = np.array([[0.2] + [0.0] * 10, [0.3] + [0.0] * 10,
                       [0.1] + [0.0] * 10])
    fidelity = np.zeros(11, dtype=bool)
    result = SearchResult(rows, scores, [], 0)
    candidates = build_candidate_sets(result, [{0}, {0}, {0}], fidelity, 0.1)
    assert set(candidates) == {0}  # (r,2r] only: 0.1 excluded, 0.2 included, 0.3 safe.
    fidelity[0] = True
    assert build_candidate_sets(result, [{0}, {0}, {0}], fidelity, 0.1) == {}


def test_lazy_equals_eager_including_ties_and_random_fill():
    rng = np.random.default_rng(1)
    ids = ["d3", "d1", "d2", "d0", "d4", "d5"]
    for _ in range(40):
        candidates = {q: (set(rng.choice(6, 3, replace=False)), float(rng.integers(1, 4))) for q in range(5)}
        eager = select_greedy(candidates, 5, np.ones(6, dtype=bool), np.random.default_rng(9), ids, False)
        lazy = select_greedy(candidates, 5, np.ones(6, dtype=bool), np.random.default_rng(9), ids, True)
        assert eager == lazy
        assert len(set(lazy[0])) == 5


def test_batch_cap_stops_on_accessed_checkpoints_and_backfill_cadence():
    assert choose_batch_cap(1000, paid=99, backfilled=64, target=100, refit_interval=50) == 1
    assert choose_batch_cap(1000, paid=84, backfilled=49, target=100, refit_interval=50) == 1
    assert choose_batch_cap(1000, paid=100, backfilled=65, target=100, refit_interval=50) == 0


def test_cgroup_ancestor_limits_override_physical_host(tmp_path):
    cg, proc = tmp_path / "cg", tmp_path / "proc"
    cg.mkdir()
    (cg / "cgroup.controllers").touch()
    (cg / "memory.max").write_text(str(1 << 30))
    (cg / "memory.current").write_text(str(1 << 28))
    (cg / "cpu.max").write_text("200000 100000")
    leaf = cg / "child"
    leaf.mkdir()
    (leaf / "memory.max").write_text("max")
    (leaf / "cpu.max").write_text("max 100000")
    (proc / "self").mkdir(parents=True)
    (proc / "self/cgroup").write_text("0::/child\n")
    limits = effective_limits(cg, proc)
    assert limits["ram_limit_bytes"] == 1 << 30
    assert limits["ram_available_bytes"] <= 3 * (1 << 28)
    assert limits["cpu_cores"] <= 2


def test_cgroup_counts_inactive_file_cache_but_never_active_or_anonymous_memory(tmp_path):
    cg, proc = tmp_path / "cg", tmp_path / "proc"
    cg.mkdir()
    (cg / "cgroup.controllers").touch()
    (cg / "memory.max").write_text(str(1 << 30))
    (cg / "memory.current").write_text(str(1 << 30))
    (cg / "memory.stat").write_text(f"inactive_file {1 << 28}\nactive_file {1 << 28}\nanon {1 << 29}\n")
    (proc / "self").mkdir(parents=True)
    (proc / "self/cgroup").write_text("0::/\n")
    assert effective_limits(cg, proc)["ram_available_bytes"] == 1 << 28


def test_h100_target_uses_visible_capacity_and_rejects_a_40gb_slice():
    cfg = load_config()
    def env(name, size):
        return {"hardware": {"devices": [{"name": name, "vram_total_bytes": int(size * (1 << 30))}]}}
    assert target_hardware_matches(cfg, env("NVIDIA H100 80GB HBM3", 79.1))
    assert not target_hardware_matches(cfg, env("NVIDIA H100 MIG 3g.40gb", 39.4))
    assert not target_hardware_matches(cfg, env("NVIDIA A100-SXM4-80GB", 79.1))


def test_bundle_is_immutable_sharded_and_rollover_is_idempotent(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    (run / "weights.bin").write_bytes(b"abcdefghijk")
    metadata = {"bytes": 11, "sha256": file_digest(run / "weights.bin")}
    bundle = ArtifactBundle("r1", run, {"run_id": "r1", "compute_status": "COMPUTE_DONE", "files": {"weights.bin": metadata}})
    prepared = prepare_bundle(bundle, tmp_path / "stage", shard_bytes=4)
    assert len(prepared.manifest["files"]) == 3
    assert prepared.manifest["originals"]["weights.bin"]["parts"] == [f"weights.bin.part-{i:05d}" for i in range(3)]
    registry = {}
    cfg = {"repo_target_files": 4, "repo_target_gib": 1, "repo_prefix": "test"}
    first = choose_upload_repo(prepared, registry, cfg, "user")
    assert len(first) == 2
    before = digest(registry)
    assert choose_upload_repo(prepared, registry, cfg, "user") == first
    assert digest(registry) == before
    (run / "weights.bin").write_bytes(b"different!!")
    assert (prepared.path / "weights.bin.part-00000").read_bytes() == b"abcd"


def test_bundle_refuses_secret_and_symlink(tmp_path):
    (tmp_path / ".env").write_text("HF_TOKEN=fixture-not-a-real-token")
    from mixindex.hf_sync import _inventory
    with pytest.raises(SyncError):
        _inventory(tmp_path)
