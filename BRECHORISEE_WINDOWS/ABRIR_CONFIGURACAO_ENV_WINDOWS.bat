@echo off
setlocal
title BRECHORISEE - Abrir .env
cd /d "%~dp0..\BRECHORISEE_SERVIDOR\app"
if not exist ".env" (
  echo Criando arquivo unico .env...
  > ".env" echo APP_ENV=local
  >> ".env" echo BRECHORISEE_ENV=local
  >> ".env" echo BRECHORISEE_STORE_NAME=BRECHORISEE
  >> ".env" echo PUBLIC_BASE_URL=http://127.0.0.1:8000
  >> ".env" echo BRECHORISEE_DB_PATH=../../dados/brechorisee.db
  >> ".env" echo BRECHORISEE_TELEGRAM_SEND_REAL=0
  >> ".env" echo BRECHORISEE_TELEGRAM_COMMANDS_ENABLED=0
)
notepad ".env"
