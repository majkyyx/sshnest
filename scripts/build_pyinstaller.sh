#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -x .venv/bin/python ]]; then
  ./scripts/dev_setup.sh
fi

. .venv/bin/activate
python -m PyInstaller \
  --noconfirm \
  --clean \
  --windowed \
  --name SshNest \
  scripts/pyinstaller_entry.py
