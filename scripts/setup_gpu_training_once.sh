#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ ! -x ".venv-wsl/bin/python" ]]; then
  echo "[ERROR] .venv-wsl not found. Create it first: python3 -m venv .venv-wsl"
  exit 1
fi

if .venv-wsl/bin/python - <<'PY'
import importlib.util
ok = all(importlib.util.find_spec(m) is not None for m in ("torch", "torchvision", "tensorboard"))
raise SystemExit(0 if ok else 1)
PY
then
  echo "[OK] GPU training packages already installed. Skipping reinstall."
else
  echo "[INFO] Installing GPU training packages (one-time)..."
  .venv-wsl/bin/python -m pip install --upgrade pip
  .venv-wsl/bin/python -m pip install --retries 20 --timeout 120 -r training/requirements-pytorch.txt
fi

.venv-wsl/bin/python - <<'PY'
import torch
print('[VERIFY] torch:', torch.__version__)
print('[VERIFY] cuda_available:', torch.cuda.is_available())
if torch.cuda.is_available():
    print('[VERIFY] device:', torch.cuda.get_device_name(0))
PY
