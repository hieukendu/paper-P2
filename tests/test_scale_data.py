import gzip
import json
from pathlib import Path

from mixindex.data.scale import _prepare_msmarco, _prepare_orcas
import mixindex.data.scale as scale


def _paths(root):
    paths = {key: str(root / key) for key in ("data", "cache", "state", "staging", "runs")}
    for value in paths.values():
        Path(value).mkdir(parents=True, exist_ok=True)
    return paths


def test_scale_ingest_preserves_body_tabs_and_joins_qrels(tmp_path, monkeypatch):
    paths = _paths(tmp_path)
    raw = Path(paths["data"]) / "raw" / "msmarco-docs-v1"
    raw.mkdir(parents=True)
    with gzip.open(raw / "msmarco-docs.tsv.gz", "wt", newline="") as stream:
        stream.write("D1\tu\tTitle\tbody\twith tab\nD2\tu2\t\tbody two\n")
    with gzip.open(raw / "msmarco-docdev-queries.tsv.gz", "wt", newline="") as stream:
        stream.write("Q1\tWhat is one?\n")
    with gzip.open(raw / "msmarco-docdev-qrels.tsv.gz", "wt", newline="") as stream:
        stream.write("Q1 0 D1 1\n")
    monkeypatch.setattr(scale, "download_dataset", lambda spec, paths: sorted(raw.iterdir()))
    spec = {"name": "msmarco-docs-v1", "parser": "msmarco_documents", "base_url": "fixture",
            "files": [p.name for p in sorted(raw.iterdir())], "documents": 2,
            "test_queries": 1, "test_qrels": 1, "source": "fixture", "license": "fixture"}
    manifest = _prepare_msmarco("msmarco-docs-v1", {"paths": paths, "splits": {"master_seed": 20261020}},
                                tmp_path, spec)
    prepared = Path(paths["data"]) / "processed" / "msmarco-docs-v1"
    assert manifest["counts"]["test_qrels"] == 1
    lines = (prepared / "documents.jsonl").read_text().splitlines()
    assert json.loads(lines[0])["text"] == "Title\nbody\twith tab"


def test_orcas_groups_deduplicate_edges_and_respect_document_join(tmp_path, monkeypatch):
    paths = _paths(tmp_path)
    raw = Path(paths["data"]) / "raw" / "msmarco-docs-v1"
    raw.mkdir(parents=True)
    for filename, rows in {
        "msmarco-docs.tsv.gz": ["D1\tu\t\tbody\n", "D2\tu\t\tbody2\n"],
        "msmarco-docdev-queries.tsv.gz": ["Q1\tjudged query\n"],
        "msmarco-docdev-qrels.tsv.gz": ["Q1 0 D1 1\n"],
    }.items():
        with gzip.open(raw / filename, "wt", newline="") as stream:
            stream.writelines(rows)
    orcas = Path(paths["data"]) / "raw" / "orcas"
    orcas.mkdir(parents=True)
    ms_spec = {"name": "msmarco-docs-v1", "parser": "msmarco_documents", "base_url": "fixture",
               "files": sorted(p.name for p in raw.iterdir()), "documents": 2,
               "test_queries": 1, "test_qrels": 1, "source": "fixture", "license": "fixture"}
    monkeypatch.setattr(
        scale,
        "download_dataset",
        lambda spec, paths: sorted(raw.iterdir()) if spec["name"] == "msmarco-docs-v1" else [orcas / "orcas.tsv.gz"],
    )
    _prepare_msmarco("msmarco-docs-v1", {"paths": paths, "splits": {"master_seed": 20261020}},
                     tmp_path, ms_spec)
    with gzip.open(orcas / "orcas.tsv.gz", "wt", newline="") as stream:
        stream.write("s1\tnew query\tD1\tu\n")
        stream.write("s2\tnew query\tD1\tu\n")
        stream.write("s2\tnew query\tD1\tu\n")
        stream.write("s3\tnew query\tD2\tu\n")
    spec = {"name": "orcas", "parser": "orcas", "url": "fixture", "md5": "fixture",
            "records": 4, "source_queries": 3, "source": "fixture", "license": "fixture"}
    manifest = _prepare_orcas("orcas", {"paths": paths, "splits": {"master_seed": 20261020}},
                              tmp_path, spec)
    assert manifest["counts"]["duplicate_edges"] == 1
    assert manifest["counts"]["missing_documents"] == 0
