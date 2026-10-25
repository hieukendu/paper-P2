import numpy as np
import pytest

from mixindex.config import load_config
from mixindex.data.splits import sample_document_pools
from mixindex.evaluation import (agreement_at_10, holm, ndcg_hit_nfr, paired_analysis,
                                 quality_auc, retained_metric)
from mixindex.index import ExactIndex
from mixindex.migration import (bootstrap_migration, emit_checkpoint, restore_migration,
                                run_migration)
from mixindex.maps import normalize, transform_global
from mixindex.vectors import PaidEmbeddingAccessor


def test_migration_resume_pending_stats_prefix_and_completion(tmp_path):
    cfg = load_config("configs/experiments/e1.yaml", overrides={"mapping": {"regional": "full", "min_region_pairs": 1}})
    rng = np.random.default_rng(42)
    old = normalize(rng.normal(size=(64, 4)))
    target = normalize(rng.normal(size=(64, 6)))
    ids = [str(i) for i in range(64)]
    pools = sample_document_pools(ids, cfg)
    heldout = set(pools["validation"])
    reserved = set(pools["train"]) | heldout
    roles = {"train": pools["train"], "validation": pools["validation"],
             "backfill": set(range(64)) - reserved}
    accessor = PaidEmbeddingAccessor(lambda rows: target[rows], roles, 64)
    state = bootstrap_migration(ids, pools, old, accessor, cfg)
    bootstrap_weights = transform_global(state.M0, old).copy()
    assert np.array_equal(state.index.vectors[sorted(reserved)], target[sorted(reserved)])
    run_migration(state, [13])
    path = emit_checkpoint(state, tmp_path, "prefix", "config-input-hash")
    resumed_accessor = PaidEmbeddingAccessor(lambda rows: target[rows], roles, 64)
    resumed = restore_migration(path, old, resumed_accessor, cfg, "config-input-hash")
    assert state.next_refit == resumed.next_refit
    assert np.array_equal(state.statistics.H, resumed.statistics.H)
    run_migration(state, [32, 64])
    run_migration(resumed, [32, 64])
    assert state.backfilled == resumed.backfilled
    assert not state.statistics.seen & heldout
    assert np.array_equal(state.index.vectors, target)
    assert np.array_equal(resumed.index.vectors, target)
    assert np.array_equal(transform_global(state.M0, old), bootstrap_weights)
    reference = ExactIndex(target, ids).search(target[:3])
    assert np.array_equal(state.index.search(target[:3]).rows, reference.rows)
    with pytest.raises(ValueError, match="incompatible"):
        restore_migration(path, old, resumed_accessor, cfg, "different-input-hash")


def test_checkpoint_detects_corrupted_state_before_serving(tmp_path):
    cfg = load_config("configs/experiments/e1.yaml")
    rng = np.random.default_rng(42)
    vectors = normalize(rng.normal(size=(20, 4)))
    ids = list(map(str, range(20)))
    pools = sample_document_pools(ids, cfg)
    accessor = PaidEmbeddingAccessor(lambda rows: vectors[rows],
        {"train": pools["train"], "validation": pools["validation"], "backfill": range(20)}, 20)
    state = bootstrap_migration(ids, pools, vectors, accessor, cfg)
    path = emit_checkpoint(state, tmp_path, "prefix", "hash")
    with (path / "state.npz").open("ab") as file:
        file.write(b"corruption")
    with pytest.raises(ValueError, match="checksum"):
        restore_migration(path, vectors, accessor, cfg, "hash")


def test_standard_ndcg_hit_nfr_zero_query_population():
    ranking = {"q": ["bad", "good"], "zero": ["bad"]}
    reference = {"q": ["good", "bad"], "zero": ["bad"]}
    qrels = {"q": {"good": 1}, "zero": {}}
    rows = ndcg_hit_nfr(ranking, qrels, reference)
    assert rows[0]["ndcg_at_10"] == pytest.approx(1 / np.log2(3))
    assert rows[0]["hit_at_10"] == 1 and rows[0]["nfr_at_1"] == 1
    assert rows[1]["ndcg_at_10"] == 0 and rows[1]["zero_idcg"]
    assert retained_metric([0], [0]) is None
    assert retained_metric([1], [0.5]) == 200


def test_agreement_auc_and_paired_inference_units():
    assert agreement_at_10([list(range(10))], [list(range(10))])[0] == 1
    assert quality_auc([0.1, 0.5], [50, 100], retained_percent=True)["auc"] == pytest.approx(0.75)
    paired = paired_analysis(np.ones(8) * 0.1, draws=100)
    assert paired["ci95"] == pytest.approx([0.1, 0.1])
    assert paired["queries"] == 8
    assert holm([0.01, 0.02, 0.9]) == pytest.approx([0.03, 0.04, 0.9])
