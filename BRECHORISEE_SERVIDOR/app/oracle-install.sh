#!/usr/bin/env bash
set -euo pipefail

# BRECHORISEE v4.9.6 - Instalador Oracle Cloud VPS Ubuntu
# Rode no servidor Oracle:
#   chmod +x oracle-install.sh
#   sudo ./oracle-install.sh

APP_USER="${APP_USER:-brechorisee}"
APP_DIR="${APP_DIR:-/opt/brechorisee}"
DATA_DIR="${DATA_DIR:-/var/lib/brechorisee}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/brechorisee}"
SERVICE_NAME="${SERVICE_NAME:-brechorisee}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
DOMAIN="${DOMAIN:-}"
PUBLIC_BASE_URL="${PUBLIC_BASE_URL:-}"

echo "============================================================"
echo "BRECHORISEE - Instalacao Oracle Cloud VPS"
echo "============================================================"

if [ "$(id -u)" -ne 0 ]; then
  echo "ERRO: rode como root/sudo: sudo ./oracle-install.sh"
  exit 1
fi

echo "[1/10] Atualizando Ubuntu e instalando pacotes..."
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  python3 python3-venv python3-pip git curl unzip rsync sqlite3 \
  nginx certbot python3-certbot-nginx ufw ca-certificates

echo "[2/10] Criando usuario e pastas..."
if ! id "$APP_USER" >/dev/null 2>&1; then
  useradd --system --create-home --shell /bin/bash "$APP_USER"
fi
mkdir -p "$APP_DIR" "$DATA_DIR/uploads" "$DATA_DIR/static/downloads" "$BACKUP_DIR"
chown -R "$APP_USER:$APP_USER" "$APP_DIR" "$DATA_DIR" "$BACKUP_DIR"

echo "[3/10] Copiando arquivos do sistema..."
CURRENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
rsync -a --delete \
  --exclude ".git" \
  --exclude "__pycache__" \
  --exclude "*.pyc" \
  "$CURRENT_DIR/" "$APP_DIR/"
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

echo "[4/10] Criando ambiente Python..."
sudo -u "$APP_USER" bash -lc "cd '$APP_DIR' && python3 -m venv .venv"
sudo -u "$APP_USER" bash -lc "cd '$APP_DIR' && .venv/bin/pip install --upgrade pip wheel setuptools"
sudo -u "$APP_USER" bash -lc "cd '$APP_DIR' && .venv/bin/pip install -r requirements.txt"

echo "[5/10] Preparando .env..."
if [ ! -f "$APP_DIR/.env" ]; then
  if [ -f "$APP_DIR/.env.oracle.example" ]; then
    cp "$APP_DIR/.env.oracle.example" "$APP_DIR/.env"
  else
    touch "$APP_DIR/.env"
  fi
fi

if [ -n "$PUBLIC_BASE_URL" ]; then
  sed -i "/^PUBLIC_BASE_URL=/d;/^BRECHORISEE_PUBLIC_BASE_URL=/d;/^TELEGRAM_WEBHOOK_URL=/d" "$APP_DIR/.env"
  {
    echo "PUBLIC_BASE_URL=$PUBLIC_BASE_URL"
    echo "BRECHORISEE_PUBLIC_BASE_URL=$PUBLIC_BASE_URL"
    echo "TELEGRAM_WEBHOOK_URL=$PUBLIC_BASE_URL/api/telegram/webhook"
  } >> "$APP_DIR/.env"
fi

grep -q "^BRECHORISEE_ENV=" "$APP_DIR/.env" || echo "BRECHORISEE_ENV=production" >> "$APP_DIR/.env"
grep -q "^BRECHORISEE_VERSION=" "$APP_DIR/.env" || echo "BRECHORISEE_VERSION=4.9.6-oracle-vps" >> "$APP_DIR/.env"
grep -q "^BRECHORISEE_DB_PATH=" "$APP_DIR/.env" || echo "BRECHORISEE_DB_PATH=$DATA_DIR/brechorisee.db" >> "$APP_DIR/.env"
grep -q "^BRECHORISEE_PERSISTENT_DIR=" "$APP_DIR/.env" || echo "BRECHORISEE_PERSISTENT_DIR=$DATA_DIR" >> "$APP_DIR/.env"

chown "$APP_USER:$APP_USER" "$APP_DIR/.env"
chmod 600 "$APP_DIR/.env"

echo "[6/10] Criando servico systemd..."
cat >/etc/systemd/system/${SERVICE_NAME}.service <<EOF
[Unit]
Description=BRECHORISEE FastAPI
After=network-online.target
Wants=network-online.target

[Service]
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${APP_DIR}
EnvironmentFile=${APP_DIR}/.env
Environment=PYTHONUNBUFFERED=1
ExecStart=${APP_DIR}/.venv/bin/uvicorn brechorisee_app.app:app --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips="*"
Restart=always
RestartSec=5
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"

echo "[7/10] Configurando Nginx..."
SERVER_NAME="_"
if [ -n "$DOMAIN" ]; then
  SERVER_NAME="$DOMAIN"
fi

cat >/etc/nginx/sites-available/brechorisee <<EOF
server {
    listen 80;
    server_name ${SERVER_NAME};

    client_max_body_size 100M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 300;
        proxy_connect_timeout 300;
        proxy_send_timeout 300;
    }
}
EOF

ln -sf /etc/nginx/sites-available/brechorisee /etc/nginx/sites-enabled/brechorisee
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl enable nginx
systemctl restart nginx

echo "[8/10] Configurando firewall do Ubuntu..."
ufw allow OpenSSH || true
ufw allow 80/tcp || true
ufw allow 443/tcp || true
ufw --force enable || true

echo "[9/10] Iniciando BRECHORISEE..."
systemctl restart "$SERVICE_NAME"
sleep 3
systemctl --no-pager --full status "$SERVICE_NAME" || true

echo "[10/10] HTTPS opcional com Certbot..."
if [ -n "$DOMAIN" ]; then
  echo "Dominio informado: $DOMAIN"
  echo "Tentando emitir HTTPS. O dominio precisa apontar para o IP publico da Oracle."
  certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m "admin@$DOMAIN" --redirect || {
    echo "Certbot nao conseguiu emitir agora. Confira DNS e rode depois:"
    echo "sudo certbot --nginx -d $DOMAIN"
  }
else
  echo "Sem DOMAIN. Use primeiro pelo IP publico em http://IP-DA-ORACLE"
  echo "Quando tiver dominio, rode:"
  echo "sudo DOMAIN=app.seudominio.com.br PUBLIC_BASE_URL=https://app.seudominio.com.br ./oracle-install.sh"
fi

echo "============================================================"
echo "INSTALACAO CONCLUIDA"
echo "Teste local no servidor: curl -I http://127.0.0.1:8000/sistema/status"
echo "Teste externo: http://IP-DA-ORACLE/sistema/status"
if [ -n "$PUBLIC_BASE_URL" ]; then
  echo "URL configurada: $PUBLIC_BASE_URL/sistema/status"
fi
echo "Logs: sudo journalctl -u ${SERVICE_NAME} -f"
echo "============================================================"
