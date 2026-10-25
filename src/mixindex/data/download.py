"""Bounded HTTP streaming and verified, traversal-safe BEIR extraction."""

import gzip
from pathlib import Path, PurePosixPath
import shutil
import stat
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import zipfile

import yaml

from ..config import project_root
from ..io import file_digest, file_lock, read_json, write_json


def dataset_spec(name, root=None) -> dict:
    registry = yaml.safe_load((project_root(root) / "configs/datasets.yaml").read_text())
    if name not in registry:
        raise ValueError(f"Unknown dataset {name}")
    return {"name": name, **registry[name]}


def verify_source_file(path, expected_digest=None) -> dict:
    path = Path(path)
    checksum = file_digest(path)
    if expected_digest:
        algorithm, value = expected_digest
        actual = checksum if algorithm == "sha256" else file_digest(path, algorithm)
        if actual != value:
            raise ValueError(f"Source checksum mismatch: {path.name}")
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as archive:
            bad = archive.testzip()
            if bad:
                raise ValueError(f"ZIP integrity failure: {bad}")
    elif path.suffix == ".gz":
        with gzip.open(path, "rb") as f:
            while f.read(8 << 20):
                pass  # Reading to EOF checks the gzip trailer and truncation.
    return {"file": path.name, "bytes": path.stat().st_size, "sha256": checksum,
            "source_checksum": list(expected_digest) if expected_digest else None}


def download_file(url, destination, expected_digest=None):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        verify_source_file(destination, expected_digest)
        return destination
    part = destination.with_suffix(destination.suffix + ".part")
    meta = part.with_suffix(part.suffix + ".json")
    for attempt in range(3):
        previous = read_json(meta) if meta.exists() else {}
        offset = part.stat().st_size if part.exists() else 0
        headers = {"User-Agent": "mixindex/0.1 (research)", "Accept-Encoding": "identity"}
        if offset and previous.get("etag"):
            headers.update(Range=f"bytes={offset}-", **{"If-Range": previous["etag"]})
        else:
            offset = 0
        try:
            with urlopen(Request(url, headers=headers), timeout=60) as response:
                etag = response.headers.get("ETag")
                resumed = bool(offset and response.status == 206 and etag == previous.get("etag")
                               and response.headers.get("Content-Range", "").startswith(f"bytes {offset}-"))
                if response.status == 206 and not resumed:
                    raise ValueError("Invalid partial response; refusing ambiguous resume")
                content_length = response.headers.get("Content-Length")
                write_json(meta, {"url": url, "etag": etag})
                received = 0
                with part.open("ab" if resumed else "wb") as output:
                    for chunk in iter(lambda: response.read(64 << 10), b""):
                        output.write(chunk)
                        received += len(chunk)
                if content_length is not None and received != int(content_length):
                    raise OSError("Incomplete download")
            verify_source_file(part, expected_digest)
            # .part has no archive suffix; validate the actual format before publishing.
            if destination.suffix == ".zip":
                with zipfile.ZipFile(part) as archive:
                    if archive.testzip():
                        raise ValueError("ZIP integrity failure")
            elif destination.suffix == ".gz":
                with gzip.open(part, "rb") as f:
                    while f.read(8 << 20):
                        pass
            part.replace(destination)
            meta.unlink(missing_ok=True)
            return destination
        except HTTPError as exc:
            if exc.code not in {408, 429, 500, 502, 503, 504} or attempt == 2:
                raise RuntimeError(f"Download failed: HTTP {exc.code}: {url}") from None
            time.sleep(min(30, int(exc.headers.get("Retry-After", 2 ** attempt))))
        except (OSError, EOFError):
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError("Download retries exhausted")


def extract_beir(archive, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        for item in z.infolist():
            path = PurePosixPath(item.filename)
            if path.is_absolute() or ".." in path.parts or "\\" in item.filename:
                raise ValueError("Unsafe archive member")
            if stat.S_ISLNK(item.external_attr >> 16):
                raise ValueError("Archive symlinks are forbidden")
            target = output.joinpath(*path.parts)
            if not target.resolve().is_relative_to(output.resolve()):
                raise ValueError("Archive traversal")
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists():
                    import zlib
                    crc = 0
                    with target.open("rb") as existing:
                        for block in iter(lambda: existing.read(4 << 20), b""):
                            crc = zlib.crc32(block, crc)
                    if target.stat().st_size != item.file_size or crc != item.CRC:
                        raise ValueError("Existing extracted file differs; preserve for inspection")
                    continue
                with z.open(item) as source, target.open("xb") as dest:
                    shutil.copyfileobj(source, dest, 4 << 20)
    return output


def download_dataset(spec, paths):
    raw = Path(paths["data"]) / "raw" / spec["name"]
    with file_lock(raw / ".download.lock"):
        urls = [spec["url"]] if "url" in spec else [spec["base_url"] + f for f in spec["files"]]
        expected = ("md5", spec["md5"]) if "md5" in spec else None
        return [download_file(url, raw / url.rsplit("/", 1)[1], expected) for url in urls]
