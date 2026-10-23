"""Run the pinned AOLIA downloader over HTTP when HTTPS is blocked locally.

The upstream downloader intentionally rewrites Wayback URLs to HTTPS.  This
wrapper changes only the transport at the requests boundary; document IDs,
capture timestamps, source mapping and parser remain those of aolia-tools.
The caller must use a separate output directory from any other downloader.
"""

import re
import runpy
from pathlib import Path
import sys

import requests


_original_get = requests.Session.get


def _http_wayback_get(session, url, *args, **kwargs):
    url = re.sub(r"^https://web\.archive\.org/web",
                 "http://web.archive.org/web", url)
    return _original_get(session, url, *args, **kwargs)


requests.Session.get = _http_wayback_get
tool = Path(__file__).resolve().parents[1] / "staging" / "aolia-tools" / "downloader.py"
if not tool.is_file():
    raise SystemExit(f"Pinned aolia-tools downloader is missing: {tool}")
sys.argv[0] = str(tool)
runpy.run_path(str(tool), run_name="__main__")
