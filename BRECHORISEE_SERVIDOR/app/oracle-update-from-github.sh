#!/usr/bin/env bash
set -euo pipefail

# Atualizador BRECHORISEE para Oracle VPS.
# Use quando o projeto estiver em GitHub:
#   sudo GIT_REPO=https://github.com/USUARIO/REPO.git ./oracle-update-from-github.sh

APP_USER="${APP_USER:-brechorisee}"
APP_DIR="${APP_DIR:-/opt/brechorisee}"
SERVICE_NAME="${SERVICE_NAME:-brechorisee}"
GIT_REPO="${GIT_REPO:-}"
BRANCH="${BRANCH:-main}"

if [ "$(id -u)" -ne 0 ]; then
  echo "ERRO: rode com sudo"
  exit 1
fi

if [ -z "$GIT_REPO" ]; then
  echo "Informe o repositorio:"
  echo "sudo GIT_REPO=https://github.com/USUARIO/REPO.git ./oracle-update-from-github.sh"
  exit 1
fi

echo "Atualizando BRECHORISEE a partir de $GIT_REPO branch $BRANCH"

if [ ! -d "$APP_DIR/.git" ]; then
  rm -rf "$APP_DIR"
  git clone --branch "$BRANCH" "$GIT_REPO" "$APP_DIR"
else
  cd "$APP_DIR"
  git fetch origin "$BRANCH"
  git reset --hard "origin/$BRANCH"
fi

chown -R "$APP_USER:$APP_USER" "$APP_DIR"

sudo -u "$APP_USER" bash -lc "cd '$APP_DIR' && python3 -m venv .venv"
sudo -u "$APP_USER" bash -lc "cd '$APP_DIR' && .venv/bin/pip install --upgrade pip wheel setuptools"
sudo -u "$APP_USER" bash -lc "cd '$APP_DIR' && .venv/bin/pip install -r requirements.txt"

systemctl daemon-reload
systemctl restart "$SERVICE_NAME"

echo "Atualizacao concluida."
echo "Veja logs: sudo journalctl -u $SERVICE_NAME -f"
