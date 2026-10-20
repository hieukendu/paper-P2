import pytest
import torch

from mixindex.nomic_adapter import CODE_REVISION, pool_nomic, verify_code_snapshot


def test_nomic_pooling_masks_padding_and_normalizes():
    hidden = torch.tensor([[[1.0, 0.0], [3.0, 0.0], [100.0, 100.0]],
                          [[0.0, 2.0], [0.0, 4.0], [0.0, 8.0]]])
    mask = torch.tensor([[1, 1, 0], [1, 0, 0]])
    plain = pool_nomic(hidden, mask, layer_norm=False)
    layered = pool_nomic(hidden, mask, layer_norm=True)
    assert torch.allclose(plain[0], torch.tensor([1.0, 0.0]), atol=1e-6)
    assert torch.allclose(plain[1], torch.tensor([0.0, 1.0]), atol=1e-6)
    assert torch.allclose(torch.linalg.norm(layered, dim=1), torch.ones(2), atol=1e-6)
    assert not torch.allclose(plain, layered)


def test_nomic_code_revision_is_pinned_before_files_are_loaded(tmp_path):
    with pytest.raises(ValueError, match="reviewed pin"):
        verify_code_snapshot(tmp_path, "unreviewed")
    assert len(CODE_REVISION) == 40
