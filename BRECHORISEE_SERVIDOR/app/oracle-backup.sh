#!/usr/bin/env bash
set -euo pipefail

DATA_DIR="${DATA_DIR:-/var/lib/brechorisee}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/brechorisee}"
APP_DIR="${APP_DIR:-/opt/brechorisee}"
STAMP="$(date +%Y%m%d_%H%M%S)"
OUT="$BACKUP_DIR/brechorisee_backup_$STAMP.tar.gz"

mkdir -p "$BACKUP_DIR"

tar -czf "$OUT" \
  "$DATA_DIR" \
  "$APP_DIR/.env" \
  2>/dev/null || true

echo "Backup criado:"
echo "$OUT"
