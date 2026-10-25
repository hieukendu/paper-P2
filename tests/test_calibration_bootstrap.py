from copy import deepcopy

import numpy as np
import pytest

from mixindex.calibration import (make_calibration_proposal, refresh_calibration,
                                  score_shadow_pairs)
from mixindex.config import load_config
from mixindex.data.splits import sample_document_pools
from mixindex.maps import fit_op, normalize, regional_validation_errors
from mixindex.migration import (bootstrap_migration, emit_checkpoint, restore_migration,
                                 run_migration)
from mixindex.vectors import PaidEmbeddingAccessor


def calibrated_fixture():
    rng = np.random.default_rng(316)
    n = 300
    ids = [f"d{r:04d}" for r in range(n)]
    cfg = load_config(overrides={"mapping": {"kind": "op"}})
    old, target = normalize(rng.normal(size=(n, 4))), normalize(rng.normal(size=(n, 6)))
    pools = sample_document_pools(ids, cfg)
    reserved = set(pools["train"]) | set(pools["validation"])
    candidates = sorted(set(range(n)) - reserved)
    cal = {}
    queries = {}
    for role, rows in (("cal_fit", candidates[:2]), ("cal_check", candidates[2:4])):
        vectors = normalize(rng.normal(size=(100, 6)))
        queries[role] = {f"{role}-{i}": v for i, v in enumerate(vectors)}
        cal[role] = {"rows": rows, "pairs": [(qid, row) for qid in queries[role] for row in rows]}
    roles = {"train": pools["train"], "validation": pools["validation"],
             "backfill": set(range(n)) - reserved}
    return ids, cfg, old, target, pools, queries, cal, roles


def test_primary_bootstrap_calibration_is_paid_disjoint_and_refreshed(tmp_path):
    ids, cfg, old, target, pools, queries, cal, roles = calibrated_fixture()
    read = []
    def source(rows):
        read.extend(rows)
        return target[rows]
    accessor = PaidEmbeddingAccessor(source, roles, len(ids))
    state = bootstrap_migration(ids, pools, old, accessor, cfg,
                                 calibration_queries=queries, fixed_calibration_pools=cal)
    bootstrap = set(pools["train"]) | set(pools["validation"]) | set(cal["cal_fit"]["rows"]) | set(cal["cal_check"]["rows"])
    assert set(read) == accessor.paid == bootstrap
    assert state.index.fidelity.sum() == len(bootstrap)
    assert np.array_equal(state.index.vectors[sorted(bootstrap)], target[sorted(bootstrap)])
    assert state.index.calibration.radius is not None
    assert state.index.calibration.a > 0
    assert not state.heldout & state.statistics.seen
    fixed_pairs = deepcopy(state.calibration_pools)
    before = state.index.calibration
    run_migration(state, [60])
    assert state.calibration_pools == fixed_pairs
    assert refresh_calibration(state) == state.index.calibration
    assert state.index.calibration != before
    assert not state.statistics.seen & state.heldout
    errors = regional_validation_errors(state, pools["validation"])
    assert sum(row["validation_pairs"] for row in errors) == len(pools["validation"])
    assert "r_vec_region" in errors[0]  # Vector-space diagnostic stays separate from score radius.
    path = emit_checkpoint(state, tmp_path, "calibrated", "inputs")
    restored_accessor = PaidEmbeddingAccessor(lambda rows: target[rows], roles, len(ids))
    resumed = restore_migration(path, old, restored_accessor, cfg, "inputs")
    assert resumed.calibration_pools == fixed_pairs
    assert resumed.index.calibration == state.index.calibration
    run_migration(state, [len(ids)])
    run_migration(resumed, [len(ids)])
    assert state.backfilled == resumed.backfilled
    assert resumed.index.calibration == state.index.calibration
    assert np.array_equal(state.index.vectors, target)
    assert np.array_equal(resumed.index.vectors, target)


def test_calibration_off_has_same_paid_pools_and_identity_residual_radius():
    ids, cfg, old, target, pools, queries, cal, roles = calibrated_fixture()
    accessor = PaidEmbeddingAccessor(lambda rows: target[rows], roles, len(ids))
    state = bootstrap_migration(ids, pools, old, accessor, cfg, calibration_queries=queries,
                                 fixed_calibration_pools=cal)
    off_cfg = deepcopy(cfg)
    off_cfg["calibration"]["enabled"] = False
    off_accessor = PaidEmbeddingAccessor(lambda rows: target[rows], roles, len(ids))
    off = bootstrap_migration(ids, pools, old, off_accessor, off_cfg, calibration_queries=queries,
                               fixed_calibration_pools=cal)
    assert accessor.paid == off_accessor.paid
    assert np.array_equal(state.index.vectors, off.index.vectors)
    assert off.index.calibration.a == 1 and off.index.calibration.b == 0
    assert off.index.calibration.reason == "disabled"
    s, t, _ = score_shadow_pairs(cal["cal_check"]["pairs"], off.M0, off.regional,
                                  off.calibration_queries, off.accessor.cache, old,
                                  off.regions["assignments"])
    expected = np.sort(np.abs(t - s))[int(np.ceil(0.95 * len(s))) - 1]
    assert off.index.calibration.radius == float(expected)


def test_common_op_proposal_respects_actual_raw_ranks_and_pools():
    ids, cfg, old, target, pools, queries, _, _ = calibrated_fixture()
    op = fit_op(old[pools["train"]], target[pools["train"]])
    caps = {"cal_fit": pools["cal_cap"], "cal_check": pools["cal_cap"]}
    reserved = set(pools["train"]) | set(pools["validation"])
    first = make_calibration_proposal(op, queries, old, ids, caps, reserved, cfg["calibration"])
    second = make_calibration_proposal(op, queries, old, ids, caps, reserved, cfg["calibration"])
    assert first == second
    from mixindex.index import ExactIndex
    from mixindex.maps import transform_global
    index = ExactIndex(transform_global(op, old, normalize=True), ids)
    used = set(reserved)
    for role, pool in first.items():
        rows = set(pool["rows"])
        assert len(rows) <= caps[role] and not rows & used
        used |= rows
        for qid, row in pool["pairs"]:
            result = index.search([queries[role][qid]], k=19, calibrated=False)
            assert row in result.rows[0, 5:20]
    corrupt = deepcopy(queries)
    qid, value = next(iter(queries["cal_fit"].items()))
    corrupt["cal_check"][qid] = value
    with pytest.raises(ValueError, match="overlap"):
        make_calibration_proposal(op, corrupt, old, ids, caps, reserved, cfg["calibration"])
