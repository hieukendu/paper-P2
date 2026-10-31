import numpy as np

from mixindex.maps import FixedProjection, transform_global
from mixindex.reviewer_aggregate import _paired_bootstrap
from mixindex.reviewer_posthoc import overlap_at_k, rbo_extrapolated


def test_overlap_and_rbo_preserve_top10_depth_gate():
    current = [str(i) for i in range(10)]
    target = [str(i) for i in range(9, -1, -1)]
    assert overlap_at_k(current, target, 1) == 0.0
    assert overlap_at_k(current, target, 10) == 1.0
    assert overlap_at_k(current, target, 20) is None
    assert rbo_extrapolated(current, target, 10, 0.9) > 0.0
    assert rbo_extrapolated(current, target, 20, 0.9) is None


def test_fixed_projection_is_dimension_safe_and_normalizable():
    model = FixedProjection(2, 3)
    values = transform_global(model, np.array([[1.0, 0.0], [0.0, 2.0]], dtype=np.float32), normalize_output=True)
    assert values.shape == (2, 3)
    assert np.allclose(values[:, 2], 0.0)
    assert np.allclose(np.linalg.norm(values, axis=1), 1.0)


def test_reviewer_paired_bootstrap_is_reproducible_and_records_unit():
    first = _paired_bootstrap([0.1, 0.2, 0.3, 0.4], "fixture")
    second = _paired_bootstrap([0.1, 0.2, 0.3, 0.4], "fixture")
    assert first == second
    assert first["effect"] == 0.25
    assert first["draws"] == 10_000
    assert first["unit"] == "query_group_conditional_on_seed_grid"
