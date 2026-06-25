#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
python3 - <<'PY'
import install
install.create_shortcut()
PY
