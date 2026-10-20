"""Restricted, verified conversion of reviewed tensor-only PyTorch checkpoints."""

from pathlib import Path
import shutil
import tempfile

from .io import digest, file_digest, file_lock, read_json, write_json


CONVERSION_VERSION = "weights-only-safetensors-v1"


def convert_reviewed_checkpoint(snapshot, cache, repo_id, revision, expected_sha256):
    """Keep upstream files immutable; publish a separate verified safetensors snapshot."""
    import torch
    from safetensors import safe_open
    from safetensors.torch import save_file
    from packaging.version import Version
    if Version(torch.__version__.split("+")[0]) < Version("2.6"):
        raise RuntimeError("Restricted checkpoint conversion requires torch >= 2.6")
    snapshot, cache = Path(snapshot), Path(cache)
    source = snapshot / "pytorch_model.bin"
    recipe = {"repo_id": repo_id, "revision": revision, "source_sha256": expected_sha256,
              "version": CONVERSION_VERSION}
    destination = cache / "converted" / digest(recipe)
    with file_lock(destination.with_suffix(".lock")):
        if destination.exists():
            record = read_json(destination / "conversion.json")
            if record["recipe"] != recipe:
                raise ValueError("Converted checkpoint recipe differs")
            for name, checksum in record["files"].items():
                if file_digest(destination / name) != checksum:
                    raise ValueError("Converted checkpoint checksum differs")
            return destination, record
        if file_digest(source) != expected_sha256:
            raise ValueError("Pinned source checkpoint checksum differs")
        unsafe = torch.serialization.get_unsafe_globals_in_checkpoint(source)
        if unsafe:
            raise ValueError("Checkpoint contains unreviewed pickle globals")
        tensors = torch.load(source, map_location="cpu", weights_only=True, mmap=True)
        if not isinstance(tensors, dict) or not tensors or any(
                not isinstance(k, str) or type(v) is not torch.Tensor for k, v in tensors.items()):
            raise ValueError("Checkpoint must contain only named tensors")
        if any(not torch.isfinite(value).all().item() for value in tensors.values()):
            raise ValueError("Checkpoint contains nonfinite weights")
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=".conversion-", dir=destination.parent))
        try:
            for file in snapshot.rglob("*"):
                if file.is_file() and file.suffix in {".json", ".txt", ".model", ".md"}:
                    target = temporary / file.relative_to(snapshot)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(file, target)
            # Cloning also removes shared-storage aliases that safetensors cannot represent.
            save_file({k: v.detach().contiguous().clone() for k, v in tensors.items()},
                      temporary / "model.safetensors", metadata={"format": "pt"})
            with safe_open(temporary / "model.safetensors", framework="pt", device="cpu") as safe:
                if set(safe.keys()) != set(tensors):
                    raise ValueError("Converted checkpoint keys differ")
                for key, original in tensors.items():
                    converted = safe.get_tensor(key)
                    if converted.dtype != original.dtype or not torch.equal(converted, original):
                        raise ValueError("Converted checkpoint tensor differs")
            record = {"recipe": recipe, "torch_version": torch.__version__,
                      "tensor_count": len(tensors), "tensor_equality": "PASS",
                      "unsafe_globals": unsafe,
                      "files": {str(p.relative_to(temporary)): file_digest(p)
                                for p in sorted(temporary.rglob("*")) if p.is_file()}}
            write_json(temporary / "conversion.json", record)
            temporary.rename(destination)
            return destination, record
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
