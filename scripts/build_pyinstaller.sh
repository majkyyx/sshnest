#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -x .venv/bin/python ]]; then
  ./scripts/dev_setup.sh
fi

.venv/bin/python -c 'import gi; gi.require_version("Gtk", "4.0"); gi.require_version("Adw", "1"); from gi.repository import Gtk, Adw' || {
  echo "GTK4 bindings are missing. Run ./scripts/dev_setup.sh; see README for native prerequisites." >&2
  exit 1
}
.venv/bin/python -m PyInstaller --noconfirm --clean scripts/sshnest.spec
