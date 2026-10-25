"""Run the pinned AOLIA downloader over HTTP when HTTPS is blocked locally.

The upstream downloader intentionally rewrites Wayback URLs to HTTPS.  This
wrapper changes only the transport at the requests boundary; document IDs,
capture timestamps, source mapping and parser remain those of aolia-tools.
The caller must use a separate output directory from any other downloader.
The accelerated recovery profile starts with one worker and a 3.5-second inter-request
delay, then ramps down by 0.5 seconds after each four clean responses to a
3-second floor.  Timeouts increase the delay again; the wrapper also honors
``Retry-After`` and applies a bounded 180–900 second 429 cooldown:
pass ``--parallel 1 --request_delay 3.5 --backoff_threshold 1
--backoff_duration 60``.  Faster profiles produced persistent Wayback 429
responses in earlier fixed-delay tests, so the adaptive controller is bounded
and starts from the last known safe profile.  The wrapper consumes the delay
option before delegating to the pinned tool. A bounded per-document retry can
be requested with ``--max_retries_per_document``; exhausted documents are
recorded in ``unavailable_ids.tsv`` and never replaced with synthetic content.
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
_minimum_request_delay = 3.0
_maximum_request_delay = 30.0
_successes_per_speedup = 4
_consecutive_429 = 0
_success_streak = 0


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
_current_request_delay = min(max(_request_delay, _minimum_request_delay),
                             _maximum_request_delay)


def _sleep_after_success():
    """Ramp down cautiously after clean responses, never below one second."""
    global _current_request_delay, _success_streak
    _success_streak += 1
    if _success_streak >= _successes_per_speedup:
        _success_streak = 0
        next_delay = max(_minimum_request_delay, _current_request_delay - 0.5)
        if next_delay < _current_request_delay:
            _current_request_delay = next_delay
            print(f"[INFO] adaptive request delay={_current_request_delay:.1f}s "
                  "after clean responses", flush=True)
    if _current_request_delay > 0:
        time.sleep(_current_request_delay)


def _sleep_after_error():
    """Add a small penalty for non-429 failures without entering a retry loop."""
    global _current_request_delay, _success_streak
    _success_streak = 0
    _current_request_delay = min(_maximum_request_delay,
                                 max(_request_delay, _current_request_delay + 1.0))
    if _current_request_delay > 0:
        time.sleep(_current_request_delay)


def _http_wayback_get(session, url, *args, **kwargs):
    global _consecutive_429, _current_request_delay, _success_streak
    url = re.sub(r"^https://web\.archive\.org/web",
                 "http://web.archive.org/web", url)
    headers = dict(kwargs.get("headers") or {})
    headers.setdefault("User-Agent", "mixindex-aolia-recovery/1.0")
    kwargs["headers"] = headers
    try:
        response = _original_get(session, url, *args, **kwargs)
    except Exception:
        _sleep_after_error()
        raise
    if response.status_code == 429:
        _consecutive_429 += 1
        _success_streak = 0
        _current_request_delay = min(_maximum_request_delay,
                                     max(_request_delay, _current_request_delay * 2.0))
        retry_after = _retry_after_seconds(response.headers.get("Retry-After"))
        exponential = min(_429_cooldown * 2 ** (_consecutive_429 - 1), _429_cooldown_max)
        cooldown = max(_current_request_delay, exponential, retry_after or 0.0)
        print(f"[WARNING] Wayback 429; wrapper cooldown={cooldown:.0f}s; "
              "honoring Retry-After when present", flush=True)
        time.sleep(cooldown)
    else:
        _consecutive_429 = 0
        _sleep_after_success()
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
