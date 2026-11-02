import warnings

import numpy as np

from mixindex.maps import FixedProjection, load_map_state, save_map_state, transform_global
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


def test_fixed_projection_checkpoint_roundtrip_preserves_outputs(tmp_path):
    model = FixedProjection(2, 3)
    inputs = np.array([[1.0, 2.0], [-2.0, 0.5]], dtype=np.float32)
    path = tmp_path / "fixed.safetensors"
    save_map_state(model, path)
    restored = load_map_state(path)
    assert np.array_equal(transform_global(model, inputs), transform_global(restored, inputs))


def test_read_only_memmap_is_copied_before_torch_conversion(tmp_path):
    path = tmp_path / "vectors.npy"
    np.save(path, np.arange(6, dtype=np.float32).reshape(3, 2))
    values = np.load(path, mmap_mode="r", allow_pickle=False)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = transform_global(FixedProjection(2, 3), values)
    assert result.shape == (3, 3)
    assert not any("not writable" in str(item.message).lower() for item in caught)


def test_reviewer_paired_bootstrap_is_reproducible_and_records_unit():
    first = _paired_bootstrap([0.1, 0.2, 0.3, 0.4], "fixture")
    second = _paired_bootstrap([0.1, 0.2, 0.3, 0.4], "fixture")
    assert first == second
    assert first["effect"] == 0.25
    assert first["draws"] == 10_000
    assert first["unit"] == "query_group_conditional_on_seed_grid"
