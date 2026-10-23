"""Write periodic, privacy-safe AOL recovery progress snapshots."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time

import psutil


def _snapshot(root):
    records = []
    for name in ("downloaded_docs", "downloaded_docs_http", "downloaded_docs_targeted",
                 "downloaded_docs_targeted_https"):
        path = root / "data/raw/aol-ia" / name
        if not path.exists():
            continue
        done_path = path / "done_ids.txt"
        done = sum(1 for _ in done_path.open()) if done_path.exists() else 0
        files = [item for item in path.iterdir() if item.is_file()]
        records.append({
            "directory": name,
            "done_ids": done,
            "shards": sum(item.suffix == ".lz4" for item in files),
            "bytes": sum(item.stat().st_size for item in files),
            "complete": (path / "_done").exists(),
        })
    processes = []
    for process in psutil.process_iter(("pid", "cmdline", "cpu_percent", "status")):
        command = " ".join(process.info.get("cmdline") or [])
        if "aolia-tools/downloader.py" in command or "scripts/download_aol_http.py" in command:
            try:
                rss = process.memory_info().rss
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                rss = None
            processes.append({
                "pid": process.info["pid"], "rss_bytes": rss,
                "cpu_percent": process.info.get("cpu_percent"),
                "status": process.info.get("status"),
                "kind": "http" if "download_aol_http.py" in command else "https",
            })
    return {"utc": datetime.now(timezone.utc).isoformat(),
            "recovery": records, "processes": processes}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--interval", type=int, default=300)
    parser.add_argument("--stop-on", default="downloaded_docs_http")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if args.interval < 1:
        raise SystemExit("interval must be positive")
    interval = args.interval
    output = args.output or args.root / "state/aol-recovery-status.jsonl"
    output.parent.mkdir(parents=True, exist_ok=True)
    while True:
        snapshot = _snapshot(args.root)
        with output.open("a") as stream:
            stream.write(json.dumps(snapshot, sort_keys=True) + "\n")
        print(json.dumps(snapshot, sort_keys=True), flush=True)
        if args.once or any(row["directory"] == args.stop_on and row["complete"]
                            for row in snapshot["recovery"]):
            return
        remaining = interval
        while remaining > 0:
            pause = min(60, remaining)
            time.sleep(pause)
            remaining -= pause


if __name__ == "__main__":
    main()
