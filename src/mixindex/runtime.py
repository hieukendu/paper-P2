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
import gc

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


def _reclaimable_file_bytes(node, version):
    fields = dict(line.split() for line in (_read(node / "memory.stat") or "").splitlines())
    # Inactive file cache is reclaimable by the kernel. Do not count anonymous memory,
    # active file pages, shared memory, or slab as freely available reservations.
    key = "inactive_file" if version == 2 else "total_inactive_file"
    return max(0, int(fields.get(key, 0)))


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
                    headrooms.append(max(0, int(maximum) - int(current) +
                                         _reclaimable_file_bytes(node, version)))
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
                                headrooms.append(max(0, int(maximum) - int(current) +
                                                     _reclaimable_file_bytes(node, version)))
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
            "host_cpu_count": psutil.cpu_count(), "cpu_cores": min(cpu_limits),
            "ram_availability_policy": "min(host_available,cgroup_limit-current+inactive_file)"}


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
            "torch_cuda": torch.version.cuda, "packages": versions, "hnsw_build": hnsw_build}


def target_hardware_matches(cfg, environment):
    devices = environment.get("hardware", {}).get("devices", [])
    # Vendors advertise nominal GB; allow the normal visible-device capacity difference.
    minimum = cfg["execution"]["target_vram_gib"] * 0.93 * (1 << 30)
    return bool(devices) and all(cfg["execution"]["target_gpu"] in device["name"] and
                                 device["vram_total_bytes"] >= minimum for device in devices)


def require_target_hardware(cfg, environment):
    if cfg["execution"]["require_target"] and not target_hardware_matches(cfg, environment):
        raise RuntimeError(f"BLOCKED_HARDWARE: target requires visible {cfg['execution']['target_gpu']} "
                           f"{cfg['execution']['target_vram_gib']}GB")


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


def probe_encoder(encoder, text_sample, batch_grid, repeats=3, gpu_headroom_gib=4, progress=None):
    """A bounded runtime probe; never returns document vectors to map selection."""
    import numpy as np
    import torch
    if not text_sample or repeats < 1 or not batch_grid:
        raise ValueError("Encoder probe needs real text samples, a batch grid and repeats")
    original = encoder.batch_size
    cuda = encoder.device.startswith("cuda")
    table = []
    try:
        encoder.batch_size = 1
        reference = encoder.encode_documents(text_sample)
        order = ([8] + sorted((b for b in batch_grid if b < 8), reverse=True) +
                 sorted(b for b in batch_grid if b > 8)) if 8 in batch_grid else batch_grid
        for batch_size in order:
            if not isinstance(batch_size, int) or batch_size < 1:
                raise ValueError("Invalid probe batch size")
            encoder.batch_size = batch_size
            if progress:
                progress(batch_size)
            try:
                encoder.encode_documents(text_sample[:min(len(text_sample), batch_size)])
                measured = []
                peak = 0
                for _ in range(repeats):
                    if cuda:
                        torch.cuda.reset_peak_memory_stats(encoder.device)
                        torch.cuda.synchronize(encoder.device)
                    before = dict(encoder.cost)
                    started = time.monotonic()
                    values = encoder.encode_documents(text_sample)
                    if cuda:
                        torch.cuda.synchronize(encoder.device)
                        peak = max(peak, torch.cuda.max_memory_allocated(encoder.device))
                    elapsed = time.monotonic() - started
                    if not np.allclose(values, reference, atol=1e-5, rtol=1e-5):
                        raise ValueError("Batch probe changed embedding values or row alignment")
                    delta = {key: encoder.cost[key] - before[key] for key in
                             ("nonpad_tokens", "padded_tokens", "truncated_documents", "calls")}
                    measured.append({"wall_seconds": elapsed, "documents_per_second": len(text_sample) / elapsed,
                                     "nonpad_tokens_per_second": delta["nonpad_tokens"] / elapsed,
                                     "padded_tokens_per_second": delta["padded_tokens"] / elapsed, **delta})
                free = total = None
                feasible = True
                if cuda:
                    free, total = torch.cuda.mem_get_info(encoder.device)
                    feasible = free >= max(gpu_headroom_gib * (1 << 30), total * 0.1)
                table.append({"batch_size": batch_size, "status": "PASS" if feasible else "HEADROOM_FAILED",
                               "median_documents_per_second": float(np.median([r["documents_per_second"] for r in measured])),
                               "peak_vram_bytes": peak, "rss_bytes": psutil.Process().memory_info().rss,
                               "device_free_bytes": free, "device_total_bytes": total,
                               "embedding_agreement": "PASS", "repeats": measured})
            except torch.cuda.OutOfMemoryError:
                table.append({"batch_size": batch_size, "status": "OOM"})
                gc.collect()
                torch.cuda.empty_cache()
            except ValueError as exc:
                table.append({"batch_size": batch_size, "status": "NUMERICAL_FAILED",
                               "reason": str(exc)})
        passing = [row for row in table if row["status"] == "PASS"]
        if not passing:
            raise RuntimeError("No encoder batch fits measured headroom")
        chosen = min(passing, key=lambda r: (-r["median_documents_per_second"], r["peak_vram_bytes"], r["batch_size"]))
        return {"selected_batch_size": chosen["batch_size"], "table": table,
                "sample_documents": len(text_sample), "role": "runtime_research",
                "device": encoder.device, "repeats": repeats,
                "adapter": {key: value for key, value in encoder.spec.items() if key != "snapshot"},
                "exclusive": "unverified", "encoder_total_cost": dict(encoder.cost)}
    finally:
        encoder.batch_size = original


def probe_threads(work_fn, grid=(1, 2, 4, 8), repeats=3, headroom=1):
    import numpy as np
    import torch
    from threadpoolctl import threadpool_limits
    limit = max(1, int(effective_limits()["cpu_cores"] - headroom))
    choices = sorted(set(int(value) for value in grid if 0 < value <= limit)) or [1]
    previous = torch.get_num_threads()
    rows = []
    try:
        for threads in choices:
            torch.set_num_threads(threads)
            with threadpool_limits(limits=threads):
                work_fn(threads)  # Warm-up is outside measurement.
                measurements = []
                for _ in range(repeats):
                    start = time.monotonic()
                    work_fn(threads)
                    measurements.append(time.monotonic() - start)
                rows.append({"threads": threads, "median_seconds": float(np.median(measurements)),
                             "repeats_seconds": measurements})
        selected = min(rows, key=lambda r: (r["median_seconds"], r["threads"]))
        return {"selected_threads": selected["threads"], "cpu_limit": limit, "table": rows}
    finally:
        torch.set_num_threads(previous)


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
