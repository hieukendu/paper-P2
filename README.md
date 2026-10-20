# MixIndex experiments

Reproducible embedding migration experiments from [codex/README.md](codex/README.md),
[report.md](report.md), and [expect.md](expect.md). Frozen encoders feed a learned
forward map, a mixed-fidelity index, and a budgeted document backfill scheduler.

The target is **H100 80GB in this workspace**, corrected by the user on 2026-10-20.
The earlier A100 requirement was a typo. Measure current visible-device, CPU, cgroup
RAM and storage limits before running; other workloads share this host. Timings from
a shared device are labeled accordingly and do not certify exclusive performance.

Implemented: validated BEIR ingestion, pinned MiniLM/MPNet snapshots, document and
query embedding caches, paid-access isolation, OP/LA/residual MLP maps, regional
ridge fitting, calibration, exact/HNSW search, adaptive greedy/random/degree/read
schedulers, exact checkpoint restore, a persistent subprocess queue, and the bounded
FiQA T0.core setup path. The root [checklist](checklist.md) records actual run status.
Scale/temporal adapters and official E2–E7 runners remain incomplete; these stages
are never marked complete from a smoke test or a small subset.

## Install and run presetup

Use Linux and Python 3.11. Dependencies are pinned in `requirements.lock.txt`, including
PyTorch 2.6.0/CUDA 12.4 and hnswlib 0.9.0 commit
`d9b3608c83d83b46c96e25088cb1d729b29dcfe9`.

```bash
bash scripts/setup.sh
source .venv/bin/activate
# Store HF_TOKEN in the local, ignored .env; existing environment variables take precedence.
mixindex probe
mixindex presetup --scope core
```

Presetup prepares and validates FiQA, downloads pinned models, checks document/query
adapters, runs E0 and the 2,000-document E1 exact completion/resume check, checks the
regional/calibration/greedy path, probes encoder batch sizes, then runs T0.core.
The queue serializes compute and waits for configured RAM/VRAM headroom. Inspect
`state/tasks.json` and `state/workers/<task_id>/stdout.log` while it runs. An unchanged
enqueue reuses immutable task IDs; changed source/configuration creates a new revision.

T0 fits OP once and tests LA/MLP learning rates `{1e-4,1e-3}` on paid train/validation
pools. It freezes common calibration pairs, checks the declared HNSW grid on independent
Q_tune, and saves learned states, local restore checks, timing, an explicit forecast,
and a scoped profile under `configs/locked/tuning.lock.yaml`. Test labels are excluded
from tuning. Missing cost measurements remain `unmeasured`; no full-scale time is invented.
ANN gate failure leaves the exact branch separate and never becomes a false recall PASS.

```bash
mixindex presetup --scope core --enqueue-only
mixindex queue --once
mixindex data validate --dataset fiqa
mixindex data validate --dataset trec-covid
pytest -q
ruff check src tests
```

## Public data and run artifacts

At the user's request, GitHub and all **project** Hugging Face repositories are public:

- [Code and pull request](https://github.com/hieukendu/paper-P2/pull/1)
- [Validated FiQA, 57,638 documents](https://huggingface.co/datasets/deadgod3005/mixindex-data-fiqa)
- [Validated TREC-COVID, 171,332 documents](https://huggingface.co/datasets/deadgod3005/mixindex-data-trec-covid)
- [Run artifacts and catalog](https://huggingface.co/datasets/deadgod3005/mixindex-runs-001)

`sync.private: false` also applies to new project repositories. Prepared releases retain
source attribution, checksums, disjoint query roles, and pinned upstream license metadata.
Run bundles contain learned maps, checkpoints, IDs, metrics, configuration and source;
pretrained checkpoints remain pinned upstream references. `.env`, credentials, raw AOL
logs and unrelated files are excluded. Uploads verify every artifact before publishing
completion markers; local copies remain intact.

```bash
mixindex data publish --dataset fiqa
mixindex data publish --dataset trec-covid
mixindex sync self-test
mixindex sync --pending
mixindex restore --receipt runs/RUN_ID/sync.json --output restored/RUN_ID
mixindex status
```

`scripts/ci-tests.yml` is an inactive GitHub Actions template: the available GitHub token
lacks the workflow scope needed to publish `.github/workflows/`. Local validation does
not claim a GitHub Actions run.
