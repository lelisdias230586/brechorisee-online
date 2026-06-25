#!/data/data/com.termux/files/usr/bin/bash
set -e

echo "=============================================="
echo " BRECHORISEE - SERVIDOR ANDROID / TERMUX"
echo "=============================================="

BASE="$HOME/brechorisee-servidor"
PACOTE="$(cd "$(dirname "$0")/.." && pwd)"
APP_SRC="$PACOTE/BRECHORISEE_SERVIDOR/app"
APP_DST="$BASE/app"
DADOS="$BASE/dados"

mkdir -p "$BASE" "$DADOS"

echo "[1/4] Atualizando Termux..."
pkg update -y
pkg install -y python clang libjpeg-turbo zlib libpng freetype git

echo "[2/4] Copiando servidor..."
rm -rf "$APP_DST"
mkdir -p "$APP_DST"
cp -R "$APP_SRC/"* "$APP_DST/" 2>/dev/null || true
cp -R "$APP_SRC"/.[!.]* "$APP_DST/" 2>/dev/null || true

if [ ! -f "$APP_DST/.env" ]; then
  cat > "$APP_DST/.env" <<EOF
APP_ENV=local
BRECHORISEE_ENV=local
BRECHORISEE_STORE_NAME=BRECHORISEE
PUBLIC_BASE_URL=http://127.0.0.1:8000
BRECHORISEE_DB_PATH=../../dados/brechorisee.db
BRECHORISEE_SECRET_KEY=troque-esta-chave-local
SECRET_KEY=troque-esta-chave-local
BRECHORISEE_SYNC_TOKEN=troque-token-sync-local
BRECHORISEE_ASSISTANT_TOKEN=troque-token-assistente-local
BRECHORISEE_TELEGRAM_SEND_REAL=0
BRECHORISEE_TELEGRAM_COMMANDS_ENABLED=0
TELEGRAM_BOT_TOKEN=COLOQUE_SEU_TOKEN_TELEGRAM_AQUI
TELEGRAM_ADMIN_CHAT_ID=COLOQUE_SEU_CHAT_ID_AQUI
TELEGRAM_ALLOWED_CHAT_IDS=COLOQUE_SEU_CHAT_ID_AQUI
TELEGRAM_WEBHOOK_SECRET=troque-webhook-local
BRECHORISEE_ANDROID_SHA256_FINGERPRINTS=COLE_O_SHA256_DO_APP_CLIENTE_AQUI
BRECHORISEE_GITHUB_DB_BACKUP=0
EOF
fi

echo "[3/4] Configurando Python..."
python -m venv "$BASE/venv"
source "$BASE/venv/bin/activate"
pip install --upgrade pip
pip install -r "$APP_DST/requirements.txt"

cat > "$BASE/iniciar_brechorisee.sh" <<EOF
#!/data/data/com.termux/files/usr/bin/bash
source "$BASE/venv/bin/activate"
cd "$APP_DST"
echo "BRECHORISEE rodando em:"
echo "http://127.0.0.1:8000"
echo "Na rede local, use o IP do celular na porta 8000."
echo "Configuracao unica: $APP_DST/.env"
python -m uvicorn brechorisee_app.app:app --host 0.0.0.0 --port 8000
EOF
chmod +x "$BASE/iniciar_brechorisee.sh"

echo "[4/4] Iniciando BRECHORISEE..."
echo "Arquivo unico de configuracao:"
echo "$APP_DST/.env"
echo
"$BASE/iniciar_brechorisee.sh"
