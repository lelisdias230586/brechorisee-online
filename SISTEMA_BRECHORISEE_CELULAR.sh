#!/data/data/com.termux/files/usr/bin/bash
set -u

VERSAO="4.9.3"
SERVER_IP="192.168.1.18"
SERVER_PORT="8000"
LOCAL_URL="http://${SERVER_IP}:${SERVER_PORT}"
TAILSCALE_URL="http://100.121.45.12:8000"
MAGICDNS_URL="http://m2012k11ag.tailabd299.ts.net:8000"
PUBLIC_URL=""

DOWNLOADS="$HOME/storage/downloads"
DEST="$HOME/brechorisee-servidor"
APP_DIR="$DEST/app"
DB_PATH="$DEST/dados/brechorisee.db"
BACKUP_DIR="$DEST/backups"
APK_DEST="$APP_DIR/brechorisee_app/static/downloads/BRECHORISEE_CLIENTE.apk"

SCRIPT_PATH="${BASH_SOURCE[0]:-$0}"
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" 2>/dev/null && pwd || pwd)"
CONFIG_FILE="$SCRIPT_DIR/SISTEMA_BRECHORISEE_CONFIG.env"
[ -f "$CONFIG_FILE" ] || CONFIG_FILE="$DOWNLOADS/SISTEMA_BRECHORISEE_CONFIG.env"

echo "============================================================"
echo " Sistema BRECHORISEE v${VERSAO} - celular servidor"
echo "============================================================"
echo "Instala/atualiza o servidor no Termux, preservando banco e .env."
echo "Publica SOMENTE o APK Cliente para download em /apk."
echo "Prepara acesso publico via SSH/localhost.run e modulo Telegram."
echo

if [ ! -d "$DOWNLOADS" ]; then
  echo "Liberando acesso aos arquivos. Toque em PERMITIR."
  termux-setup-storage || true
  sleep 3
fi

if [ -f "$CONFIG_FILE" ]; then
  . "$CONFIG_FILE" 2>/dev/null || true
fi

[ -z "${LOCAL_URL:-}" ] && LOCAL_URL="http://${SERVER_IP}:${SERVER_PORT}"
[ -z "${TAILSCALE_URL:-}" ] && TAILSCALE_URL="http://100.121.45.12:8000"
[ -z "${MAGICDNS_URL:-}" ] && MAGICDNS_URL="http://m2012k11ag.tailabd299.ts.net:8000"
[ -z "${PUBLIC_URL:-}" ] && PUBLIC_URL="$TAILSCALE_URL"

echo "Pasta do script: $SCRIPT_DIR"
echo "Servidor local: ${LOCAL_URL}"
echo "Servidor Tailscale: ${TAILSCALE_URL}"
echo "MagicDNS: ${MAGICDNS_URL}"
echo "Publico atual: ${PUBLIC_URL}"
echo

find_source() {
  for CAND in \
    "$SCRIPT_DIR/BRECHORISEE_SERVIDOR" \
    "$SCRIPT_DIR/PACOTE_CELULAR_SERVIDOR/BRECHORISEE_SERVIDOR" \
    "$DOWNLOADS/BRECHORISEE_SERVIDOR" \
    "$DOWNLOADS/PACOTE_CELULAR_SERVIDOR/BRECHORISEE_SERVIDOR" \
    "$DOWNLOADS/PACOTE_CELULAR_SERVIDOR/PACOTE_CELULAR_SERVIDOR/BRECHORISEE_SERVIDOR" \
    "$DOWNLOADS/brechorisee-servidor"; do
    if [ -d "$CAND/app" ]; then
      echo "$CAND"
      return 0
    fi
  done

  FOUND="$(find "$DOWNLOADS" "$SCRIPT_DIR" -maxdepth 5 -type d -name BRECHORISEE_SERVIDOR 2>/dev/null | while read -r d; do [ -d "$d/app" ] && echo "$d" && break; done)"
  if [ -n "$FOUND" ]; then
    echo "$FOUND"
    return 0
  fi
  return 1
}

SOURCE="$(find_source || true)"
if [ -z "$SOURCE" ]; then
  echo "ERRO: nao encontrei a pasta BRECHORISEE_SERVIDOR com app."
  echo
  echo "Copie o CONTEUDO da pasta PACOTE_CELULAR_SERVIDOR para Downloads do celular,"
  echo "ou execute este script dentro da pasta onde esta BRECHORISEE_SERVIDOR."
  echo
  echo "Arquivos encontrados em Downloads:"
  find "$DOWNLOADS" -maxdepth 3 -type d -o -type f 2>/dev/null | sed 's#^#- #' | head -80
  exit 1
fi

echo "Servidor encontrado: $SOURCE"
echo

echo "Instalando pacotes Termux..."
pkg update -y
pkg install -y python python-numpy python-pillow net-tools openssl-tool unzip openssh
pkg install -y cloudflared >/dev/null 2>&1 || true

echo "Preservando banco, .env, backup e APK antigo..."
TMP_KEEP="$HOME/.brechorisee_keep_$$"
mkdir -p "$TMP_KEEP"
if [ -f "$DB_PATH" ]; then
  mkdir -p "$TMP_KEEP/dados"
  cp -f "$DB_PATH" "$TMP_KEEP/dados/brechorisee.db"
  echo "Banco preservado."
fi
if [ -f "$APP_DIR/.env" ]; then
  cp -f "$APP_DIR/.env" "$TMP_KEEP/.env"
  echo ".env preservado."
fi
if [ -f "$APK_DEST" ]; then
  mkdir -p "$TMP_KEEP/downloads"
  cp -f "$APK_DEST" "$TMP_KEEP/downloads/BRECHORISEE_CLIENTE.apk"
  echo "APK Cliente publicado anterior preservado."
fi
if [ -d "$BACKUP_DIR" ]; then
  mkdir -p "$TMP_KEEP/backups"
  cp -r "$BACKUP_DIR"/. "$TMP_KEEP/backups/" 2>/dev/null || true
fi

echo "Atualizando servidor na area interna do Termux..."
rm -rf "$DEST"
cp -r "$SOURCE" "$DEST"

if [ ! -f "$APP_DIR/requirements.txt" ]; then
  echo "ERRO: requirements.txt nao encontrado em $APP_DIR"
  ls -la "$DEST" || true
  exit 1
fi

mkdir -p "$DEST/dados" "$DEST/backups" "$APP_DIR/brechorisee_app/static/downloads"

if [ -f "$TMP_KEEP/dados/brechorisee.db" ]; then
  cp -f "$TMP_KEEP/dados/brechorisee.db" "$DB_PATH"
fi
if [ -d "$TMP_KEEP/backups" ]; then
  cp -r "$TMP_KEEP/backups"/. "$BACKUP_DIR/" 2>/dev/null || true
fi

cd "$APP_DIR" || exit 1

echo "Configurando .env sem apagar Telegram existente..."
if [ -f "$TMP_KEEP/.env" ]; then
  cp -f "$TMP_KEEP/.env" .env
elif [ ! -f .env ]; then
  cat > .env <<EOF
APP_ENV=production
BRECHORISEE_ENV=production
BRECHORISEE_STORE_NAME=BRECHORISEE
BRECHORISEE_TELEGRAM_SEND_REAL=0
BRECHORISEE_TELEGRAM_COMMANDS_ENABLED=1
TELEGRAM_BOT_TOKEN=
TELEGRAM_ADMIN_CHAT_ID=
TELEGRAM_ALLOWED_CHAT_IDS=
TELEGRAM_WEBHOOK_SECRET=
BRECHORISEE_SECRET_KEY=troque-esta-chave-local
SECRET_KEY=troque-esta-chave-local
SYNC_TOKEN=troque-sync-local
BRECHORISEE_ASSISTANT_TOKEN=troque-assistente-local
EOF
fi

upsert_env() {
  key="$1"
  val="$2"
  touch .env
  tmp=".env.tmp.$$"
  if grep -q "^${key}=" .env 2>/dev/null; then
    awk -v k="$key" -v v="$val" 'BEGIN{FS=OFS="="} $1==k {$0=k"="v} {print}' .env > "$tmp"
  else
    cat .env > "$tmp"
    printf '%s=%s\n' "$key" "$val" >> "$tmp"
  fi
  mv "$tmp" .env
}

upsert_env "APP_ENV" "production"
upsert_env "BRECHORISEE_ENV" "production"
upsert_env "BRECHORISEE_VERSION" "${VERSAO}-apk-assinado-validado"
upsert_env "BRECHORISEE_STORE_NAME" "BRECHORISEE"
upsert_env "PUBLIC_BASE_URL" "$PUBLIC_URL"
upsert_env "BRECHORISEE_PUBLIC_BASE_URL" "$PUBLIC_URL"
upsert_env "BRECHORISEE_PUBLIC_URL" "$PUBLIC_URL"
upsert_env "BRECHORISEE_LOCAL_URL" "$LOCAL_URL"
upsert_env "BRECHORISEE_TAILSCALE_URL" "$TAILSCALE_URL"
upsert_env "BRECHORISEE_MAGICDNS_URL" "$MAGICDNS_URL"
upsert_env "BRECHORISEE_SERVER_URL" "$LOCAL_URL"
upsert_env "BRECHORISEE_ADMIN_SERVER_URL" "$LOCAL_URL"
upsert_env "BRECHORISEE_CLIENT_SERVER_URL" "$LOCAL_URL"
upsert_env "BRECHORISEE_DB_PATH" "$DB_PATH"
upsert_env "BRECHORISEE_BACKUP_DIR" "$BACKUP_DIR"
upsert_env "BRECHORISEE_HOST" "0.0.0.0"
upsert_env "BRECHORISEE_PORT" "$SERVER_PORT"

validar_apk() {
  arquivo="$1"
  python - "$arquivo" <<'PY'
import sys, zipfile, os
p = sys.argv[1]
try:
    if not os.path.isfile(p) or os.path.getsize(p) < 16 * 1024:
        print("INVALIDO: arquivo pequeno/inexistente")
        sys.exit(1)
    if not zipfile.is_zipfile(p):
        print("INVALIDO: nao e ZIP/APK")
        sys.exit(1)
    with zipfile.ZipFile(p) as z:
        names = set(z.namelist())
        upper_names = {n.upper() for n in names}
        if "AndroidManifest.xml" not in names:
            print("INVALIDO: sem AndroidManifest.xml")
            sys.exit(1)
        dex_names = [n for n in names if n.startswith("classes") and n.endswith(".dex")]
        if not dex_names:
            print("INVALIDO: sem classes.dex")
            sys.exit(1)

        # Bloqueia APK release sem assinatura. Esse e o motivo mais comum do erro:
        # "Como o pacote parece ser invalido, o app nao foi instalado."
        has_v1_cert = any(n.startswith("META-INF/") and (n.endswith(".RSA") or n.endswith(".DSA") or n.endswith(".EC")) for n in upper_names)
        if not has_v1_cert:
            print("INVALIDO: APK sem assinatura/certificado. Nao use app-release-unsigned.apk; gere pelo GERAR_APK_CLIENTE_FINAL_WINDOWS.bat.")
            sys.exit(1)

        markers = (b"Lcom/brechorisee/cliente/MainActivity;", b"com/brechorisee/cliente/MainActivity")
        found = False
        for dex in dex_names:
            data = z.read(dex)
            if any(m in data for m in markers):
                found = True
                break
        if not found:
            print("INVALIDO: APK antigo/incompativel, falta com.brechorisee.cliente.MainActivity no classes.dex")
            sys.exit(1)
    print("OK")
except Exception as exc:
    print("INVALIDO:", exc)
    sys.exit(1)
PY
}

echo "Publicando APK Cliente no servidor..."
APK_SRC=""
for CAND in \
  "$SCRIPT_DIR/BRECHORISEE_CLIENTE.apk" \
  "$SCRIPT_DIR/PACOTE_CELULAR_SERVIDOR/BRECHORISEE_CLIENTE.apk" \
  "$DOWNLOADS/BRECHORISEE_CLIENTE.apk" \
  "$DOWNLOADS/PACOTE_CELULAR_SERVIDOR/BRECHORISEE_CLIENTE.apk" \
  "$DOWNLOADS/PACOTE_CELULAR_SERVIDOR/PACOTE_CELULAR_SERVIDOR/BRECHORISEE_CLIENTE.apk" \
  "$SOURCE/app/brechorisee_app/static/downloads/BRECHORISEE_CLIENTE.apk" \
  "$TMP_KEEP/downloads/BRECHORISEE_CLIENTE.apk"; do
  if [ -f "$CAND" ] && validar_apk "$CAND" >/dev/null 2>&1; then
    APK_SRC="$CAND"
    break
  fi
done

if [ -z "$APK_SRC" ]; then
  APK_SRC="$(find "$DOWNLOADS" "$SCRIPT_DIR" -maxdepth 6 -type f \( -iname '*CLIENTE*.apk' -o -iname '*cliente*.apk' -o -iname '*app-release*.apk' -o -iname '*release*.apk' \) 2>/dev/null | while read -r f; do validar_apk "$f" >/dev/null 2>&1 && echo "$f" && break; done)"
fi

if [ -n "$APK_SRC" ] && [ -f "$APK_SRC" ]; then
  mkdir -p "$(dirname "$APK_DEST")"
  cp -f "$APK_SRC" "$APK_DEST"
  chmod 644 "$APK_DEST" 2>/dev/null || true
  echo "OK: APK Cliente valido publicado:"
  echo "$APK_DEST"
  ls -lh "$APK_DEST"
else
  echo "AVISO: APK Cliente novo/compativel nao encontrado."
  echo "O site vai funcionar pelo navegador, mas o botao de APK ficara desativado ate publicar um APK valido."
  echo "Depois copie BRECHORISEE_CLIENTE.apk para Downloads do celular e rode:"
  echo "bash ~/PUBLICAR_APK_CLIENTE_BRECHORISEE.sh"
  rm -f "$APK_DEST" 2>/dev/null || true
fi

echo "Garantindo que APK Admin NAO fique publicado para clientes..."
rm -f "$APP_DIR/brechorisee_app/static/downloads/BRECHORISEE_ADMIN.apk" 2>/dev/null || true

echo "Criando script de publicacao rapida do APK Cliente..."
cat > "$HOME/PUBLICAR_APK_CLIENTE_BRECHORISEE.sh" <<'EOS'
#!/data/data/com.termux/files/usr/bin/bash
set -u
DOWNLOADS="$HOME/storage/downloads"
APP_DIR="$HOME/brechorisee-servidor/app"
APK_DEST="$APP_DIR/brechorisee_app/static/downloads/BRECHORISEE_CLIENTE.apk"
mkdir -p "$(dirname "$APK_DEST")"

validar_apk() {
  arquivo="$1"
  python - "$arquivo" <<'PY'
import sys, zipfile, os
p = sys.argv[1]
try:
    if not os.path.isfile(p) or os.path.getsize(p) < 16 * 1024:
        print("INVALIDO: arquivo pequeno/inexistente")
        sys.exit(1)
    if not zipfile.is_zipfile(p):
        print("INVALIDO: nao e ZIP/APK")
        sys.exit(1)
    with zipfile.ZipFile(p) as z:
        names = set(z.namelist())
        upper_names = {n.upper() for n in names}
        if "AndroidManifest.xml" not in names:
            print("INVALIDO: sem AndroidManifest.xml")
            sys.exit(1)
        dex_names = [n for n in names if n.startswith("classes") and n.endswith(".dex")]
        if not dex_names:
            print("INVALIDO: sem classes.dex")
            sys.exit(1)

        # Bloqueia APK release sem assinatura. Esse e o motivo mais comum do erro:
        # "Como o pacote parece ser invalido, o app nao foi instalado."
        has_v1_cert = any(n.startswith("META-INF/") and (n.endswith(".RSA") or n.endswith(".DSA") or n.endswith(".EC")) for n in upper_names)
        if not has_v1_cert:
            print("INVALIDO: APK sem assinatura/certificado. Nao use app-release-unsigned.apk; gere pelo GERAR_APK_CLIENTE_FINAL_WINDOWS.bat.")
            sys.exit(1)

        markers = (b"Lcom/brechorisee/cliente/MainActivity;", b"com/brechorisee/cliente/MainActivity")
        found = False
        for dex in dex_names:
            data = z.read(dex)
            if any(m in data for m in markers):
                found = True
                break
        if not found:
            print("INVALIDO: APK antigo/incompativel, falta com.brechorisee.cliente.MainActivity no classes.dex")
            sys.exit(1)
    print("OK")
except Exception as exc:
    print("INVALIDO:", exc)
    sys.exit(1)
PY
}

APK_SRC="$(find "$DOWNLOADS" -maxdepth 6 -type f \( -iname '*CLIENTE*.apk' -o -iname '*cliente*.apk' -o -iname '*app-release*.apk' -o -iname '*release*.apk' \) 2>/dev/null | while read -r f; do validar_apk "$f" >/dev/null 2>&1 && echo "$f" && break; done)"
if [ -z "$APK_SRC" ] || [ ! -f "$APK_SRC" ]; then
  echo "ERRO: nao encontrei APK Cliente VALIDO em Downloads."
  echo "O arquivo precisa ser APK Cliente NOVO ASSINADO: ZIP valido, AndroidManifest.xml, classes.dex, assinatura/certificado e com.brechorisee.cliente.MainActivity."
  echo "Gere o APK pelo projeto Android ou copie BRECHORISEE_CLIENTE.apk valido para Downloads."
  exit 1
fi
cp -f "$APK_SRC" "$APK_DEST"
chmod 644 "$APK_DEST" 2>/dev/null || true
echo "OK: APK Cliente valido publicado em:"
echo "$APK_DEST"
ls -lh "$APK_DEST"
EOS
chmod +x "$HOME/PUBLICAR_APK_CLIENTE_BRECHORISEE.sh"

cat > "$HOME/CONFIGURAR_LINK_PUBLICO_BRECHORISEE.sh" <<'EOS'
#!/data/data/com.termux/files/usr/bin/bash
set -u
URL="${1:-}"
APP_DIR="$HOME/brechorisee-servidor/app"
ENV_FILE="$APP_DIR/.env"
if [ -z "$URL" ]; then
  echo "Uso:"
  echo "bash ~/CONFIGURAR_LINK_PUBLICO_BRECHORISEE.sh https://SEU-LINK.lhr.life"
  exit 1
fi
case "$URL" in
  http://*|https://*) ;;
  *) echo "ERRO: informe a URL completa, começando com http:// ou https://"; exit 1;;
esac
mkdir -p "$APP_DIR"
touch "$ENV_FILE"
upsert_env() {
  key="$1"; val="$2"; tmp="$ENV_FILE.tmp.$$"
  if grep -q "^${key}=" "$ENV_FILE" 2>/dev/null; then
    awk -v k="$key" -v v="$val" 'BEGIN{FS=OFS="="} $1==k {$0=k"="v} {print}' "$ENV_FILE" > "$tmp"
  else
    cat "$ENV_FILE" > "$tmp"
    printf '%s=%s\n' "$key" "$val" >> "$tmp"
  fi
  mv "$tmp" "$ENV_FILE"
}
upsert_env "PUBLIC_BASE_URL" "$URL"
upsert_env "BRECHORISEE_PUBLIC_BASE_URL" "$URL"
upsert_env "BRECHORISEE_PUBLIC_URL" "$URL"
upsert_env "BRECHORISEE_CLIENT_APK_URL" "$URL/download/app-cliente.apk"
upsert_env "BRECHORISEE_CLIENT_APP_URL" "$URL/app/cliente"
upsert_env "BRECHORISEE_APP_DOWNLOAD_URL" "$URL/app/cliente"
echo "OK: link publico salvo em $ENV_FILE"
echo "$URL"
echo "Reinicie o servidor: CTRL+C e depois bash ~/INICIAR_SISTEMA_BRECHORISEE.sh"
EOS
chmod +x "$HOME/CONFIGURAR_LINK_PUBLICO_BRECHORISEE.sh"

cat > "$HOME/INICIAR_SISTEMA_BRECHORISEE_SSH_PUBLICO.sh" <<'EOS'
#!/data/data/com.termux/files/usr/bin/bash
set -u
PORTA="${BRECHORISEE_PORT:-8000}"
echo "============================================================"
echo " BRECHORISEE - TUNEL PUBLICO SSH / localhost.run"
echo "============================================================"
echo "Mantenha o servidor aberto em outra sessao:"
echo "bash ~/INICIAR_SISTEMA_BRECHORISEE.sh"
echo
echo "Quando aparecer https://....lhr.life, esse sera o link externo."
echo "Nesta versão, os botoes do site usam automaticamente o dominio atual."
echo "Para Telegram/mensagens geradas fora do navegador, salve o link com:"
echo "bash ~/CONFIGURAR_LINK_PUBLICO_BRECHORISEE.sh https://SEU-LINK.lhr.life"
echo
pkg install -y openssh >/dev/null 2>&1 || true
ssh -R 80:127.0.0.1:${PORTA} nokey@localhost.run
EOS
chmod +x "$HOME/INICIAR_SISTEMA_BRECHORISEE_SSH_PUBLICO.sh"

echo "Criando ambiente Python compativel..."
echo "Criando ambiente Python compativel..."
rm -rf venv
python -m venv --system-site-packages venv
. venv/bin/activate
pip install --upgrade pip setuptools wheel

echo "Instalando dependencias leves compativeis com Android/Termux..."
pip uninstall -y fastapi pydantic pydantic-core starlette >/dev/null 2>&1 || true
pip install "pydantic==1.10.24" "fastapi==0.95.2" "starlette==0.27.0"
pip install "uvicorn==0.30.6" "jinja2==3.1.4" "python-multipart==0.0.9" "qrcode==7.4.2" "httpx==0.27.0" "itsdangerous==2.2.0"

cat > "$HOME/INICIAR_SISTEMA_BRECHORISEE.sh" <<EOF
#!/data/data/com.termux/files/usr/bin/bash
cd "$APP_DIR" || exit 1
. venv/bin/activate
echo "============================================================"
echo " Sistema BRECHORISEE - SERVIDOR CELULAR"
echo "============================================================"
echo "Local:     ${LOCAL_URL}"
echo "Tailscale: ${TAILSCALE_URL}"
echo "MagicDNS:  ${MAGICDNS_URL}"
echo "Publico:   ${PUBLIC_URL}"
echo "Admin:     ${LOCAL_URL}/admin"
echo "Cliente:   ${LOCAL_URL}/app/cliente"
echo "APK:       ${LOCAL_URL}/apk"
echo
echo "Nao feche o Termux enquanto o servidor estiver em uso."
echo "Para parar: CTRL + C"
echo
uvicorn brechorisee_app.app:app --host 0.0.0.0 --port ${SERVER_PORT}
EOF
chmod +x "$HOME/INICIAR_SISTEMA_BRECHORISEE.sh"

cat > "$HOME/INICIAR_BRECHORISEE_SERVIDOR.sh" <<EOF
#!/data/data/com.termux/files/usr/bin/bash
bash "$HOME/INICIAR_SISTEMA_BRECHORISEE.sh"
EOF
chmod +x "$HOME/INICIAR_BRECHORISEE_SERVIDOR.sh"

cat > "$HOME/INICIAR_SISTEMA_BRECHORISEE_PUBLICO.sh" <<'EOF'
#!/data/data/com.termux/files/usr/bin/bash
set -u
APP_DIR="$HOME/brechorisee-servidor/app"
cd "$APP_DIR" || exit 1
. venv/bin/activate
echo "============================================================"
echo " Sistema BRECHORISEE - LINK PUBLICO PARA CLIENTES"
echo "============================================================"
echo "Vou iniciar o servidor local e abrir um link HTTPS publico."
echo "Quando aparecer https://....trycloudflare.com, use esse link para:"
echo "Sistema, Admin, Cliente e /apk."
echo
if ! command -v cloudflared >/dev/null 2>&1; then
  echo "Instalando cloudflared..."
  pkg install -y cloudflared || {
    echo "Nao consegui instalar cloudflared automaticamente."
    echo "Alternativa: usar Tailscale para equipe ou configurar dominio/tunel depois."
    exit 1
  }
fi
if ! pgrep -f "uvicorn brechorisee_app.app:app" >/dev/null 2>&1; then
  echo "Iniciando servidor BRECHORISEE em segundo plano..."
  nohup uvicorn brechorisee_app.app:app --host 0.0.0.0 --port 8000 > "$HOME/brechorisee-servidor-publico.log" 2>&1 &
  sleep 5
fi
echo "Abrindo Cloudflare Tunnel..."
echo "Copie o link HTTPS que aparecer abaixo."
cloudflared tunnel --url http://127.0.0.1:8000
EOF
chmod +x "$HOME/INICIAR_SISTEMA_BRECHORISEE_PUBLICO.sh"

cat > "$HOME/BRECHORISEE_STATUS.txt" <<EOF
Sistema BRECHORISEE v${VERSAO}
Local: ${LOCAL_URL}
Tailscale: ${TAILSCALE_URL}
MagicDNS: ${MAGICDNS_URL}
Publico: ${PUBLIC_URL}
Admin local: ${LOCAL_URL}/admin
Cliente local: ${LOCAL_URL}/app/cliente
APK local: ${LOCAL_URL}/apk
APK tailscale: ${TAILSCALE_URL}/apk
Cloudflare publico: bash ~/INICIAR_SISTEMA_BRECHORISEE_PUBLICO.sh
Banco: ${DB_PATH}
EOF

rm -rf "$TMP_KEEP"

echo
echo "============================================================"
echo " Sistema BRECHORISEE v${VERSAO} pronto"
echo "============================================================"
echo "Local: ${LOCAL_URL}"
echo "Tailscale: ${TAILSCALE_URL}"
echo "MagicDNS: ${MAGICDNS_URL}"
echo "Admin: ${LOCAL_URL}/admin"
echo "Cliente: ${LOCAL_URL}/app/cliente"
echo "APK Cliente: ${LOCAL_URL}/apk"
echo "APK Cliente Tailscale: ${TAILSCALE_URL}/apk"
echo
echo "Para link publico via SSH sem Cloudflare e sem abrir porta:"
echo "bash ~/INICIAR_SISTEMA_BRECHORISEE_SSH_PUBLICO.sh"
echo
echo "Para link publico via Cloudflare:"
echo "bash ~/INICIAR_SISTEMA_BRECHORISEE_PUBLICO.sh"
echo
echo "Vou iniciar o servidor agora."
echo "Para parar: CTRL + C"
echo
bash "$HOME/INICIAR_SISTEMA_BRECHORISEE.sh"
