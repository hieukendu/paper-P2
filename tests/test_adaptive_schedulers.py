import numpy as np
import pytest

from mixindex.index import SearchResult, select_search_config, ExactIndex
from mixindex.maps import normalize
from mixindex.migration import bootstrap_migration, emit_checkpoint, restore_migration, run_migration
from mixindex.scheduling import SchedulingTraffic, select_on_read
from mixindex.vectors import PaidEmbeddingAccessor
from test_calibration_bootstrap import calibrated_fixture


def test_on_read_preserves_pending_order_across_capped_batches():
    calls = []
    def search(query):
        calls.append(query)
        rows = np.array([np.arange(11)])
        return SearchResult(rows, np.zeros_like(rows), [], 0)
    state, mapped = {}, np.ones(12, dtype=bool)
    first, _ = select_on_read(["q0", "q1"], search, 2, state, mapped, np.random.default_rng(1))
    assert first == [0, 1] and calls == ["q0"]
    mapped[first] = False
    second, meta = select_on_read(["q0", "q1"], search, 2, state, mapped, np.random.default_rng(1))
    assert second == [2, 3] and calls == ["q0"]
    assert meta["read_count"] == 2


@pytest.mark.parametrize("kind", ["greedy", "read", "degree", "random"])
def test_all_primary_schedulers_resume_and_refresh_only_needed_queries(kind, tmp_path):
    ids, cfg, old, target, pools, queries, cal, roles = calibrated_fixture()
    cfg["scheduler"]["kind"] = kind
    rng = np.random.default_rng(91)
    qvectors = normalize(rng.normal(size=(9, 6)))
    proxies = None if kind != "degree" else [set(range(i, i + 3)) for i in range(9)]
    traffic = SchedulingTraffic(tuple(f"schedule-{i}" for i in range(9)), qvectors, proxies)
    accessor = PaidEmbeddingAccessor(lambda rows: target[rows], roles, len(ids))
    state = bootstrap_migration(ids, pools, old, accessor, cfg, calibration_queries=queries,
                                 fixed_calibration_pools=cal)
    first = run_migration(state, [30], traffic=traffic)
    refreshed = [r for r in state.cost_records if r["component"] == "scheduling_full_refresh"]
    if kind == "greedy":
        assert len(refreshed) == len(first["events"])
        assert all(r["queries_refreshed"] == 9 for r in refreshed)
    else:
        assert not refreshed
    path = emit_checkpoint(state, tmp_path, "scheduler-prefix", "input-hash")
    resumed_accessor = PaidEmbeddingAccessor(lambda rows: target[rows], roles, len(ids))
    resumed = restore_migration(path, old, resumed_accessor, cfg, "input-hash")
    run_migration(state, [60], traffic=traffic)
    run_migration(resumed, [60], traffic=traffic)
    assert state.backfilled == resumed.backfilled
    assert state.read_state == resumed.read_state
    assert np.array_equal(state.index.vectors, resumed.index.vectors)
    changed = SchedulingTraffic(tuple(f"changed-{i}" for i in range(9)), qvectors)
    with pytest.raises(ValueError, match="traffic changed"):
        run_migration(resumed, [90], traffic=changed)


def test_scheduler_traffic_rejects_wrong_role_or_nonfinite_weights():
    values = normalize(np.ones((1, 3)))
    with pytest.raises(PermissionError):
        SchedulingTraffic(("test-q",), values, role="eval")
    with pytest.raises(ValueError, match="weights"):
        SchedulingTraffic(("q",), values, weights=np.array([np.nan]))


def test_search_selection_needs_all_variants_and_never_calls_transfer_a_pass(monkeypatch):
    vectors = normalize(np.random.default_rng(5).normal(size=(60, 4)))
    snapshot = ExactIndex(vectors, list(map(str, range(60))))
    selected = select_search_config({"OP": snapshot, "MLP": snapshot}, vectors[:3], [[50, 200], [100, 200]])
    assert selected["status"] == "PASS" and selected["candidates"] == 50
    assert len(selected["table"]) == 4
    transfer = select_search_config({}, np.empty((0, 4)), [[50, 200]])
    assert transfer["status"] == "UNTUNED_TRANSFER" and not transfer["table"]
    import mixindex.index as index_module
    def failed(ann, exact, query):
        return {"candidate_recall_at_11": 0.98, "serving_recall_at_10": 1.0, "raw_recall_at_10": 1.0}
    monkeypatch.setattr(index_module, "validate_ann_snapshot", failed)
    result = select_search_config({"variant": snapshot}, vectors[:3], [[50, 200], [100, 200]])
    assert result["status"] == "ANN_GATE_FAILED" and result["candidates"] is None
