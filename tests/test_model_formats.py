from pathlib import Path

import pytest
import torch
from safetensors.torch import load_file

from mixindex.io import file_digest
from mixindex.model_formats import convert_reviewed_checkpoint


def test_restricted_conversion_preserves_aliases_values_and_snapshot_integrity(tmp_path):
    source = tmp_path / "snapshot"
    source.mkdir()
    original = torch.arange(12, dtype=torch.float32).reshape(3, 4)
    torch.save({"weight": original, "alias": original[:, :2]}, source / "pytorch_model.bin")
    (source / "config.json").write_text('{"model_type":"fixture"}')
    checksum = file_digest(source / "pytorch_model.bin")
    output, record = convert_reviewed_checkpoint(source, tmp_path / "cache", "fixture", "rev", checksum)
    converted = load_file(output / "model.safetensors")
    assert torch.equal(converted["weight"], original)
    assert torch.equal(converted["alias"], original[:, :2])
    assert record["tensor_equality"] == "PASS" and record["tensor_count"] == 2
    assert not (output / "pytorch_model.bin").exists()
    assert file_digest(source / "pytorch_model.bin") == checksum
    assert convert_reviewed_checkpoint(source, tmp_path / "cache", "fixture", "rev", checksum)[0] == output
    (output / "model.safetensors").write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="checksum differs"):
        convert_reviewed_checkpoint(source, tmp_path / "cache", "fixture", "rev", checksum)


def test_conversion_rejects_source_tamper_objects_and_nonfinite_weights(tmp_path):
    source = tmp_path / "snapshot"
    source.mkdir()
    checkpoint = source / "pytorch_model.bin"
    torch.save({"weight": torch.ones(2)}, checkpoint)
    with pytest.raises(ValueError, match="source checkpoint checksum"):
        convert_reviewed_checkpoint(source, tmp_path / "cache", "fixture", "rev", "bad")
    torch.save({"unexpected_object": Path("not-a-tensor")}, checkpoint)
    with pytest.raises(ValueError, match="unreviewed pickle globals"):
        convert_reviewed_checkpoint(source, tmp_path / "cache", "fixture", "rev", file_digest(checkpoint))
    torch.save({"weight": torch.tensor([float("nan")])}, checkpoint)
    with pytest.raises(ValueError, match="nonfinite"):
        convert_reviewed_checkpoint(source, tmp_path / "cache", "fixture", "rev", file_digest(checkpoint))
