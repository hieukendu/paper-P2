# MixIndex experiments

Implementation of the embedding migration protocol in [codex/README.md](codex/README.md),
[report.md](report.md), and [expect.md](expect.md). Frozen document encoders feed a learned
forward map, a mixed-fidelity index, and a budgeted backfill scheduler. No encoder training
or language generation is involved.

The current implementation provides validated BEIR ingestion, revision-pinned model downloads,
an embedding-access ledger, OP/LA/residual maps, regional ridge statistics, calibration,
exact/HNSW search, coverage selection, exact migration checkpoints, and private Hub publishing.
The CLI currently wires preparation, probes, sync/restore and the E1 exact vertical slice.
Primary calibration/bootstrap, the complete queue, T0 runtime selection, and E2–E7 runners
are still being integrated. See the root [checklist](checklist.md) for actual run status.

Official measurements target an **A100 80GB**. The initial development workspace exposes an
H100 and does not certify A100 readiness, T0 tuning, or official experiment results.
CPU tests verify correctness only. No paper placeholder is treated as an observed result.
`scripts/ci-tests.yml` is an inactive GitHub Actions template; the current GitHub token lacks
the workflow scope needed to publish it under `.github/workflows/`.

Use Python 3.11 on Linux. The checked dependency lock uses PyTorch 2.6.0/CUDA 12.4 and
hnswlib 0.9.0 at commit `d9b3608c83d83b46c96e25088cb1d729b29dcfe9`.
Check the actual driver/device with `mixindex probe` after installation on the target server.

```bash
bash scripts/setup.sh
source .venv/bin/activate
# Put HF_TOKEN in the project .env; existing environment variables take precedence.
mixindex data prepare --dataset fiqa
mixindex models prepare --pair minilm_mpnet --dataset fiqa
mixindex sync self-test
mixindex run --experiment E1 --config configs/experiments/e1.yaml
```

For an explicitly labeled correctness diagnostic on other hardware:

```bash
OMP_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4 mixindex run --experiment E1 \
  --config configs/experiments/e1.yaml --development-hardware
```

Prepared data are immutable and checked against complete source counts, archive checksums,
schema, ID joins and disjoint normalized query roles. Vector caches retain row IDs and
adapter/revision keys. All new document embeddings used by migration pass through
`PaidEmbeddingAccessor`; evaluator references are separate and their compute is research cost.

Run bundles use private `OWNER/mixindex-runs-NNN` dataset repositories. Payload digests are
verified before completion markers; `sync.json` pins remote commits for restore. Local copies
remain intact. Raw corpora and pretrained checkpoints are excluded from automatic run uploads.
Explicit `mixindex data publish --dataset fiqa` publishes validated processed FiQA separately,
with upstream attribution and the declared CC BY-SA 4.0 terms.

```bash
mixindex data validate --dataset fiqa
mixindex data publish --dataset fiqa
mixindex sync --pending
mixindex restore --receipt runs/RUN_ID/sync.json --output restored/RUN_ID
mixindex status
pytest -q
```

Source documents: [BEIR FiQA](https://huggingface.co/datasets/BeIR/fiqa),
[hnswlib v0.9.0](https://github.com/nmslib/hnswlib/tree/v0.9.0),
[Hub upload/verification API](https://huggingface.co/docs/huggingface_hub/package_reference/hf_api).

Agent triển khai bắt đầu từ [codex/README.md](codex/README.md), đọc đầy đủ [report.md](report.md) và [expect.md](expect.md), rồi làm theo [codex/plan.md](codex/plan.md). Tiến độ ở [checklist.md](checklist.md).

Hiện là bộ đặc tả, chưa có implementation hoặc thí nghiệm đã chạy. Target: server A100 80GB; validate inputs, smoke và tuning/freeze trước official experiments.
