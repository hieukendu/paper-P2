"""Run the pinned AOLIA downloader over HTTP when HTTPS is blocked locally.

The upstream downloader intentionally rewrites Wayback URLs to HTTPS.  This
wrapper changes only the transport at the requests boundary; document IDs,
capture timestamps, source mapping and parser remain those of aolia-tools.
The caller must use a separate output directory from any other downloader.
The current conservative recovery profile is one worker with a 5-second
inter-request delay and a 60-second pinned-tool backoff after one error; the
wrapper additionally honors ``Retry-After`` and applies a bounded 180–900
second 429 cooldown:
pass ``--parallel 1 --request_delay 5.0 --backoff_threshold 1
--backoff_duration 60``.  Faster profiles produced persistent Wayback 429
responses, so they are not used for this recovery run.  The wrapper consumes
the delay option before delegating to the pinned tool.
"""

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import re
import runpy
from pathlib import Path
import sys
import time

import requests


_original_get = requests.Session.get
_429_cooldown = 180.0
_429_cooldown_max = 900.0
_consecutive_429 = 0


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


def _retry_after_seconds(value):
    """Parse an HTTP Retry-After value without trusting malformed headers."""
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        pass
    try:
        retry_at = parsedate_to_datetime(value)
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=timezone.utc)
        return max(0.0, (retry_at - datetime.now(timezone.utc)).total_seconds())
    except (TypeError, ValueError, OverflowError):
        return None


_request_delay, sys.argv = _take_request_delay(sys.argv)


def _http_wayback_get(session, url, *args, **kwargs):
    global _consecutive_429
    url = re.sub(r"^https://web\.archive\.org/web",
                 "http://web.archive.org/web", url)
    headers = dict(kwargs.get("headers") or {})
    headers.setdefault("User-Agent", "mixindex-aolia-recovery/1.0")
    kwargs["headers"] = headers
    try:
        response = _original_get(session, url, *args, **kwargs)
    except Exception:
        if _request_delay > 0:
            time.sleep(_request_delay)
        raise
    if response.status_code == 429:
        _consecutive_429 += 1
        retry_after = _retry_after_seconds(response.headers.get("Retry-After"))
        exponential = min(_429_cooldown * 2 ** (_consecutive_429 - 1), _429_cooldown_max)
        cooldown = max(_request_delay, exponential, retry_after or 0.0)
        print(f"[WARNING] Wayback 429; wrapper cooldown={cooldown:.0f}s; "
              "honoring Retry-After when present", flush=True)
        time.sleep(cooldown)
    else:
        _consecutive_429 = 0
        if _request_delay > 0:
            time.sleep(_request_delay)
    return response


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
