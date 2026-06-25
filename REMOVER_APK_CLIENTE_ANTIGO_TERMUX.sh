#!/data/data/com.termux/files/usr/bin/bash
set -u
APK="$HOME/brechorisee-servidor/app/brechorisee_app/static/downloads/BRECHORISEE_CLIENTE.apk"
echo "Removendo APK Cliente antigo publicado no servidor..."
rm -f "$APK"
echo "OK. O site não vai mais oferecer APK antigo."
echo "Use pelo navegador em /cliente/inicio ou /app/cliente até compilar e publicar o APK novo v4.8.8."
