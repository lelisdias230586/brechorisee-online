#!/data/data/com.termux/files/usr/bin/bash
BASE="$HOME/brechorisee-servidor"
source "$BASE/venv/bin/activate"
cd "$BASE/app"
echo "BRECHORISEE rodando em http://127.0.0.1:8000"
echo "Configuracao unica: $BASE/app/.env"
python -m uvicorn brechorisee_app.app:app --host 0.0.0.0 --port 8000
