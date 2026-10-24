from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

import mixindex.experiments_static as static
from mixindex.config import load_config
from mixindex.data.splits import sample_document_pools
from mixindex.data.store import build_document_store
from mixindex.evaluation import StaticEvaluator
from mixindex.index import ExactIndex
from mixindex.io import digest, read_json, write_json
from mixindex.maps import normalize
from mixindex.migration import bootstrap_migration, emit_checkpoint
from mixindex.vectors import PaidEmbeddingAccessor


def test_evaluator_owns_reference_and_emits_only_a_technical_gate(tmp_path):
    import io
    vectors = normalize(np.random.default_rng(8).normal(size=(20, 4)))
    ids = [f"d{i:02d}" for i in range(20)]
    queries = vectors[:2]
    labels = {"q0": {ids[0]: 1}, "q1": {ids[1]: 1}}
    evaluator = StaticEvaluator(vectors, vectors, ids, list(labels), queries, queries, labels)
    output = io.StringIO()
    index = ExactIndex(vectors, ids, np.ones(20, dtype=bool))
    gate = evaluator.evaluate_snapshot(index, 20, 18, output)
    assert gate == {"checkpoint_complete": True}
    assert all(row["arr_at_10"] == 1 for row in evaluator.records)
    assert all(row["ndcg_at_10"] == 1 for row in evaluator.records)
    evaluator.verify_completion(index)
    bad = ExactIndex(-vectors, ids, np.ones(20, dtype=bool))
    with pytest.raises(ValueError, match="100% true"):
        evaluator.verify_completion(bad)


def _fixture(tmp_path, monkeypatch):
    import mixindex.encoders as encoders
    cfg = load_config()
    cfg["paths"] = {key: str(tmp_path / key) for key in cfg["paths"]}
    cfg["sync"]["enabled"] = False
    cfg["execution"].update(device="cpu", phase="official", mode="cached_access")
    cfg["experiment"]["profile_hash"] = "fixture-profile"
    cfg["mapping"].update(max_epochs=2, rank=2, hidden=8, min_region_pairs=2)
    prepared = tmp_path / "data/processed/fiqa"
    n, dim = 80, 8
    ids = [f"d{i:03d}" for i in range(n)]
    build_document_store([(did, "", f"doc{i}") for i, did in enumerate(ids)], prepared)
    roles = {"schedule": ["train_a", "train_b"], "cal_fit": [], "cal_check": [],
             "tune": ["tune_a"], "eval": ["test_a", "test_b"]}
    write_json(prepared / "splits/query_roles.json", {"roles": roles})
    groups = [{"group_id": qid, "text": qid, "representative_id": qid}
              for values in roles.values() for qid in values]
    pq.write_table(pa.Table.from_pylist(groups), prepared / "queries.parquet")
    qrels = [{"split": split, "group_id": qid, "doc_id": ids[i], "doc_row": i, "grade": 1}
             for split, qid, i in [("train", "train_a", 1), ("train", "train_b", 2),
                                  ("test", "test_a", 3), ("test", "test_b", 4)]]
    pq.write_table(pa.Table.from_pylist(qrels), prepared / "qrels.parquet")
    manifest = {"release_hash": "fixture", "split_hash": digest(roles)}
    write_json(prepared / "manifest.json", manifest)
    old = normalize(np.random.default_rng(32).normal(size=(n, dim)))
    specs = {role: {"repo_id": role, "dim": dim, "snapshot": "fixture", "resolved_revision": "fixed"}
             for role in ("old", "new")}
    class Encoder:
        def __init__(self, spec, device, batch_size):
            self.spec, self.batch_size = spec, batch_size
            self.cost = {"documents": 0}
        def encode_documents(self, texts):
            self.cost["documents"] += len(texts)
            return np.stack([old[int(text[3:])] if text.startswith("doc") else
                             old[int(digest(text)[:6], 16) % n] for text in texts])
        encode_queries = encode_documents
        def close(self):
            pass
    monkeypatch.setattr(static, "build_encoder", Encoder)
    monkeypatch.setattr(encoders, "build_encoder", Encoder)
    monkeypatch.setattr(static, "_old_vectors", lambda *args: old)
    environment = {"fixture": "environment"}
    monkeypatch.setattr(static, "probe_hardware", lambda: environment)
    pools = sample_document_pools(ids, cfg)
    reserved = set(pools["train"]) | set(pools["validation"])
    accessor = PaidEmbeddingAccessor(lambda rows: old[rows], {"train": pools["train"],
            "validation": pools["validation"], "backfill": set(range(n)) - reserved}, n)
    state = bootstrap_migration(ids, pools, old, accessor, cfg)
    source = tmp_path / "runs/T0-fixture"
    emit_checkpoint(state, source / "checkpoints", "bootstrap-op", "source-fixture")
    profile = {"scope": "core", "inputs": {"release": "fixture"}, "selections": {
        "map": {kind: {"lr": None if kind == "op" else .001} for kind in ("op", "la", "residual_mlp")}}}
    monkeypatch.setattr(static, "_profile_context", lambda *args: (profile, source, prepared, manifest, specs))
    (tmp_path / "checklist.md").write_text("<!-- progress:begin -->\n<!-- progress:end -->\n")
    return cfg, profile, source, prepared


def test_static_preflight_and_official_cell_keep_test_labels_out_until_preflight(tmp_path, monkeypatch):
    cfg, profile, source, prepared = _fixture(tmp_path, monkeypatch)
    original = pq.read_table
    test_reads = []
    def guarded(path, *args, **kwargs):
        if Path(path).name == "qrels.parquet":
            filters = kwargs.get("filters")
            assert filters in [[("split", "=", "train")], [("split", "=", "test")]]
            if filters == [("split", "=", "test")]:
                test_reads.append(path)
                assert allow_test[0], "Preflight opened test labels"
        return original(path, *args, **kwargs)
    allow_test = [False]
    monkeypatch.setattr(static.pq, "read_table", guarded)
    preflight = static.run_static_preflight(cfg, tmp_path)
    assert preflight["compute_status"] == "COMPUTE_DONE", preflight
    assert preflight["checked_cells"] == 9
    assert preflight["local_restore"] == "PASS"
    assert not test_reads
    cfg["experiment"]["preflight_run"] = preflight["run_id"]
    allow_test[0] = True
    result = static.run_static_cell(cfg, tmp_path)
    assert result["compute_status"] == "COMPUTE_DONE", result
    assert result["phase"] == "official" and result["unique_paid_documents"] == 80
    assert result["completion_exact_agreement"] == 1.
    assert test_reads
    run = tmp_path / "runs" / result["run_id"]
    metrics = original(run / "metrics.parquet").to_pylist()
    assert all(row["phase"] == "official" for row in metrics)
    assert all(row["arr_at_10"] == 1 for row in metrics if row["checkpoint"] == "accessed-000000080")
    assert read_json(run / "reference_inputs.json")["cost_scope"].startswith("evaluator/research")
    assert len(list((run / "checkpoints").glob("accessed-*"))) == 6
    # A changed scientific input/source cannot open labels under an older preflight.
    cfg["experiment"]["preflight_run"] = None
    with pytest.raises(ValueError, match="E2_PREFLIGHT_REQUIRED"):
        static.run_static_cell(cfg, tmp_path)


def test_static_matrix_has_all_declared_cells_and_concrete_dependencies(tmp_path, monkeypatch):
    cfg, profile, source, _ = _fixture(tmp_path, monkeypatch)
    cfg["search"]["threads"] = 8
    profile["selections"]["runtime"] = {"threads": {"selected_threads": 8}, "batches": {"new": 64}}
    write_json(tmp_path / "state/tasks.json", {"tasks": {"T0.core.concrete": {
        "spec": {"task_id": "T0.core.concrete"}, "run_dir": str(source), "status": "COMPUTE_DONE"}}})
    tasks = static.build_static_tasks(cfg, tmp_path)
    assert len(tasks) == 25
    assert tasks[0]["experiment"] == "E2_PREFLIGHT"
    assert tasks[0]["depends_on"] == ["T0.core.concrete"]
    preflight_identity = {
        "config": static.redacted_config(tasks[0]["config_overrides"]),
        "source_hash": static.source_hash(tmp_path),
        "profile_hash": cfg["experiment"]["profile_hash"],
        "input_refs": profile["inputs"],
        "run_budget_policy": static.RUN_BUDGET_POLICY,
        "comparison_variants": {"primary": list(static.VARIANTS["primary"])},
    }
    expected_preflight = f"E2_PREFLIGHT-fiqa-{static.digest(preflight_identity)[:12]}"
    assert all(t["config_overrides"]["experiment"]["preflight_run"] == expected_preflight
               for t in tasks[1:] if t["dataset_case"] == "fiqa")
    assert tasks[1]["config_overrides"]["scheduler"]["kind"] == "random"
    assert len([t for t in tasks[1:] if t["dataset_case"] == "fiqa" and
                t["cell_role"] == "scheduler" and
                t["config_overrides"]["mapping"]["kind"] == "residual_mlp" and
                t["config_overrides"]["scheduler"]["kind"] in {"random", "degree", "read", "greedy"}]) == 12
    assert len([t for t in tasks[1:] if t["dataset_case"] == "trec-covid"]) == 3
    assert len({t["task_id"] for t in tasks}) == 25
    mapping = [t for t in tasks[1:] if t["dataset_case"] == "fiqa" and
               t["cell_role"] == "mapping" and
               t["config_overrides"]["mapping"]["kind"] in {"op", "la", "residual_mlp"} and
               t["config_overrides"]["scheduler"]["kind"] == "random"]
    scheduler = [t for t in tasks[1:] if t["dataset_case"] == "fiqa" and
                 t["cell_role"] == "scheduler" and
                 t["config_overrides"]["mapping"]["kind"] == "residual_mlp" and
                 t["config_overrides"]["scheduler"]["kind"] in {"random", "degree", "read", "greedy"}]
    assert len(mapping) == 9 and len(scheduler) == 12
    assert all(set(t["depends_on"]) >= {tasks[0]["task_id"]} for t in tasks[1:])
    assert all(set(t["depends_on"]) >= {m["task_id"] for m in mapping} for t in scheduler)
    assert all(mapping[i - 1]["task_id"] in mapping[i]["depends_on"]
               for i in range(1, len(mapping)))
    assert all(scheduler[i - 1]["task_id"] in scheduler[i]["depends_on"]
               for i in range(1, len(scheduler)))
