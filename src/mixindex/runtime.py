"""Effective resource probes and explicit measurement scopes."""

from contextlib import contextmanager
import importlib.metadata
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile
import time

import psutil

from .io import file_digest


def _read(path):
    try:
        return Path(path).read_text().strip()
    except (OSError, PermissionError):
        return None


def _cpus(value):
    result = set()
    for item in value.split(","):
        a, _, b = item.partition("-")
        result.update(range(int(a), int(b or a) + 1))
    return result


def effective_limits(cgroup_root=Path("/sys/fs/cgroup"), proc_root=Path("/proc")) -> dict:
    host = psutil.virtual_memory()
    memory_limits = [host.total]
    headrooms = [host.available]
    cpu_limits = [float(len(os.sched_getaffinity(0)))]
    version = 2 if (cgroup_root / "cgroup.controllers").exists() else 1
    memberships = (_read(proc_root / "self/cgroup") or "").splitlines()
    if version == 2:
        relative = next((line.split(":", 2)[2] for line in memberships
                         if line.startswith("0::")), "/")
        leaf = cgroup_root / relative.lstrip("/")
        if not leaf.exists():
            leaf = cgroup_root  # A container may mount its own cgroup as the root.
        nodes = [leaf, *(p for p in leaf.parents if p.is_relative_to(cgroup_root))]
        for node in nodes:
            maximum, current = _read(node / "memory.max"), _read(node / "memory.current")
            if maximum and maximum != "max":
                memory_limits.append(int(maximum))
                if current:
                    headrooms.append(max(0, int(maximum) - int(current)))
            quota = _read(node / "cpu.max")
            if quota:
                amount, period = quota.split()
                if amount != "max":
                    cpu_limits.append(int(amount) / int(period))
            cpuset = _read(node / "cpuset.cpus.effective")
            if cpuset:
                cpu_limits.append(float(len(_cpus(cpuset))))
    else:
        for line in memberships:
            _, controllers, relative = line.split(":", 2)
            for controller in controllers.split(","):
                mount = cgroup_root / controller
                if controller == "cpu" and not mount.exists():
                    mount = cgroup_root / "cpu,cpuacct"
                leaf = mount / relative.lstrip("/")
                if not leaf.exists():
                    leaf = mount
                for node in [leaf, *(p for p in leaf.parents if p.is_relative_to(mount))]:
                    if controller == "memory":
                        maximum = _read(node / "memory.limit_in_bytes")
                        current = _read(node / "memory.usage_in_bytes")
                        if maximum and int(maximum) < (1 << 60):
                            memory_limits.append(int(maximum))
                            if current:
                                headrooms.append(max(0, int(maximum) - int(current)))
                    if controller == "cpu":
                        quota = _read(node / "cpu.cfs_quota_us")
                        period = _read(node / "cpu.cfs_period_us")
                        if quota and period and int(quota) > 0:
                            cpu_limits.append(int(quota) / int(period))
                    if controller == "cpuset":
                        cpuset = _read(node / "cpuset.cpus")
                        if cpuset:
                            cpu_limits.append(float(len(_cpus(cpuset))))
    return {"cgroup_version": version, "host_ram_bytes": host.total,
            "ram_limit_bytes": min(memory_limits),
            "ram_available_bytes": min(headrooms + [min(memory_limits)]),
            "host_cpu_count": psutil.cpu_count(), "cpu_cores": min(cpu_limits)}


def probe_hardware() -> dict:
    import torch
    gpu = []
    cuda_error = None
    try:
        if torch.cuda.is_available():
            for index in range(torch.cuda.device_count()):
                properties = torch.cuda.get_device_properties(index)
                free, total = torch.cuda.mem_get_info(index)
                # Properties describe the device visible to this process, including MIG slices.
                with torch.cuda.device(index):
                    x = torch.ones(8, device=f"cuda:{index}")
                    assert (x + x).sum().item() == 16
                gpu.append({"device": index, "name": properties.name,
                            "vram_total_bytes": total, "vram_free_bytes": free,
                            "sm_count": properties.multi_processor_count,
                            "compute_capability": list(torch.cuda.get_device_capability(index)),
                            "cuda_smoke": "PASS"})
    except Exception as exc:
        cuda_error = type(exc).__name__
    if shutil.which("nvidia-smi"):
        smi = subprocess.run(["nvidia-smi", "--query-gpu=name,driver_version,mig.mode.current",
                              "--format=csv,noheader"], capture_output=True, text=True, check=False)
        driver = smi.stdout.strip().splitlines() if smi.returncode == 0 else []
    else:
        driver = []
    versions = {}
    for name in ("torch", "numpy", "scipy", "transformers", "sentence-transformers",
                 "huggingface-hub", "hnswlib", "pyarrow", "scikit-learn"):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    hnsw_build = None
    try:
        import hnswlib
        distribution = importlib.metadata.distribution("hnswlib")
        import json
        provenance = json.loads(distribution.read_text("direct_url.json") or "{}")
        hnsw_build = {"sha256": file_digest(Path(hnswlib.__file__)),
                      "source": provenance.get("url"),
                      "commit": provenance.get("vcs_info", {}).get("commit_id")}
    except ImportError:
        pass
    return {"python": platform.python_version(), "platform": platform.system(),
            "hardware": {"devices": gpu, "physical_inventory": driver,
                         "cuda_error": cuda_error, "exclusive": "unverified",
                         **effective_limits()},
            "torch_cuda": torch.version.cuda, "packages": versions, "hnsw_build": hnsw_build,
            "target_a100_80gb": bool(gpu) and all(
                "A100" in g["name"] and g["vram_total_bytes"] >= 75 * (1 << 30) for g in gpu)}


def require_target_hardware(cfg, environment):
    if cfg["execution"]["require_target"] and not environment["target_a100_80gb"]:
        raise RuntimeError("BLOCKED_HARDWARE: official target requires visible A100 80GB; "
                           "this host is development only")


def probe_storage(work_dir: Path, bytes_to_write=16 << 20) -> dict:
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".mixindex-probe-", dir=work_dir)
    path = Path(name)
    try:
        block = os.urandom(min(bytes_to_write, 1 << 20))
        start = time.monotonic()
        with os.fdopen(fd, "wb") as f:
            remaining = bytes_to_write
            while remaining:
                chunk = block[:remaining]
                f.write(chunk)
                remaining -= len(chunk)
            f.flush()
            os.fsync(f.fileno())
        write_seconds = time.monotonic() - start
        start = time.monotonic()
        checksum = file_digest(path)
        read_seconds = time.monotonic() - start
        usage = shutil.disk_usage(work_dir)
        return {"bytes": bytes_to_write, "write_fsync_seconds": write_seconds,
                "read_sha256_seconds": read_seconds, "sha256": checksum,
                "free_bytes": usage.free, "device_id": work_dir.stat().st_dev,
                "cache_policy": "read may be served by page cache"}
    finally:
        path.unlink(missing_ok=True)


@contextmanager
def cost_scope(name, records=None, cuda=False):
    import torch
    if cuda:
        torch.cuda.synchronize()
    start, cpu = time.monotonic(), time.process_time()
    record = {"component": name}
    try:
        yield record
    finally:
        if cuda:
            torch.cuda.synchronize()
        record.update(wall_seconds=time.monotonic() - start,
                      cpu_seconds=time.process_time() - cpu,
                      rss_bytes=psutil.Process().memory_info().rss)
        if records is not None:
            records.append(record)
