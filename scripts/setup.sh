#!/usr/bin/env bash
set -euo pipefail

# Run from any directory. The lock is for Python 3.11 and CUDA 12.4 on Linux.
PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"
python3.11 -m venv .venv
PIP_CONFIG_FILE=/dev/null PIP_EXTRA_INDEX_URL='' .venv/bin/python -m pip install \
  --index-url https://pypi.org/simple -r requirements.lock.txt
.venv/bin/python -m pip install -e . --no-deps
.venv/bin/python -m pip check
.venv/bin/mixindex probe --config configs/base.yaml
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 .venv/bin/python -m pytest -q
