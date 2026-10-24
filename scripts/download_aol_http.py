"""Run the pinned AOLIA downloader over HTTP when HTTPS is blocked locally.

The upstream downloader intentionally rewrites Wayback URLs to HTTPS.  This
wrapper changes only the transport at the requests boundary; document IDs,
capture timestamps, source mapping and parser remain those of aolia-tools.
The caller must use a separate output directory from any other downloader.
The validated conservative recovery profile is one worker with a 0.5-second
inter-request delay (plus the pinned downloader's retry/backoff controls):
pass ``--parallel 1 --request_delay 0.5``.  A zero delay caused repeated
Wayback 5xx responses in the bounded canary, so it must not be used for a
recovery run.  The wrapper consumes the delay option before delegating to the
pinned tool.
"""

import re
import runpy
from pathlib import Path
import sys
import time

import requests


_original_get = requests.Session.get


def _take_request_delay(argv):
    """Remove the wrapper-only delay option before invoking aolia-tools."""
    remaining = [argv[0]]
    delay = 0.0
    index = 1
    while index < len(argv):
        value = argv[index]
        if value == "--request_delay":
            if index + 1 >= len(argv):
                raise SystemExit("--request_delay requires a non-negative number")
            delay = float(argv[index + 1])
            index += 2
            continue
        if value.startswith("--request_delay="):
            delay = float(value.split("=", 1)[1])
            index += 1
            continue
        remaining.append(value)
        index += 1
    if delay < 0:
        raise SystemExit("--request_delay must be non-negative")
    return delay, remaining


_request_delay, sys.argv = _take_request_delay(sys.argv)


def _http_wayback_get(session, url, *args, **kwargs):
    url = re.sub(r"^https://web\.archive\.org/web",
                 "http://web.archive.org/web", url)
    try:
        return _original_get(session, url, *args, **kwargs)
    finally:
        if _request_delay > 0:
            time.sleep(_request_delay)


requests.Session.get = _http_wayback_get
tool = Path(__file__).resolve().parents[1] / "staging" / "aolia-tools" / "downloader.py"
if not tool.is_file():
    raise SystemExit(f"Pinned aolia-tools downloader is missing: {tool}")
sys.argv[0] = str(tool)


def _run_pinned_downloader():
    """Resume after the pinned sequential-backoff ``pool`` bug.

    The pinned downloader calls ``pool.terminate()`` after consecutive HTTP
    failures even when ``--parallel 1`` selected the built-in ``map`` path.
    Its checkpoint file is append-only, so retrying the top-level invocation
    is safe and resumes only IDs that are not already recorded.
    """
    while True:
        try:
            runpy.run_path(str(tool), run_name="__main__")
            return
        except UnboundLocalError as error:
            if "local variable 'pool'" not in str(error):
                raise
            print("[WARNING] pinned sequential downloader backoff bug; "
                  "resuming from done_ids.txt after 30 seconds", flush=True)
            time.sleep(30.0)


_run_pinned_downloader()
