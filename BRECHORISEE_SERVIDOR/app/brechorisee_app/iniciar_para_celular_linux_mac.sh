#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
if [ ! -x ".venv/bin/python" ]; then
  echo "Primeira abertura: instalando dependências..."
  python3 install.py
fi

URL="http://127.0.0.1:8000/celular"
".venv/bin/python" mostrar_endereco.py || true

if command -v xdg-open >/dev/null 2>&1; then
  (sleep 2; xdg-open "$URL" >/dev/null 2>&1 || true) &
elif command -v open >/dev/null 2>&1; then
  (sleep 2; open "$URL" >/dev/null 2>&1 || true) &
fi

".venv/bin/python" app.py
