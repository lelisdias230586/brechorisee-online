#!/usr/bin/env bash
set -euo pipefail

# Compila o APK Cliente e copia para o servidor/site.
# Requer Android SDK instalado e Gradle disponível no PATH, ou Android Studio.
# No Termux puro geralmente NÃO existe Android SDK; compile no Windows/Android Studio.

ROOT="$(cd "$(dirname "$0")" && pwd)"
ANDROID_DIR="$ROOT/BRECHORISEE_CLIENTE/android"
SERVER_APK="$ROOT/BRECHORISEE_SERVIDOR/app/brechorisee_app/static/downloads/BRECHORISEE_CLIENTE.apk"

echo "== BRECHORISEE Cliente APK v4.8.9 =="
echo "Projeto Android: $ANDROID_DIR"

if [ ! -d "$ANDROID_DIR/app/src/main" ]; then
  echo "ERRO: projeto Android Cliente não encontrado."
  exit 1
fi

if [ -z "${ANDROID_HOME:-}" ] && [ -z "${ANDROID_SDK_ROOT:-}" ]; then
  echo "ERRO: ANDROID_HOME/ANDROID_SDK_ROOT não configurado."
  echo "Instale Android Studio ou Android SDK e configure a variável de ambiente."
  exit 2
fi

if [ -x "$ANDROID_DIR/gradlew" ]; then
  GRADLE_CMD="./gradlew"
elif command -v gradle >/dev/null 2>&1; then
  GRADLE_CMD="gradle"
else
  echo "ERRO: Gradle não encontrado."
  echo "Instale Gradle ou abra o projeto no Android Studio."
  exit 3
fi

cd "$ANDROID_DIR"

rm -rf app/build/outputs/apk

# Debug é assinado automaticamente. Release assinado deve ser gerado no Windows pelo script
# GERAR_APK_CLIENTE_FINAL_WINDOWS.bat ou com keystore.properties configurado.
if [ "$GRADLE_CMD" = "./gradlew" ]; then
  ./gradlew --no-daemon clean assembleDebug
else
  gradle --no-daemon clean assembleDebug
fi

APK_SRC="$ANDROID_DIR/app/build/outputs/apk/debug/app-debug.apk"
if [ ! -f "$APK_SRC" ]; then
  echo "ERRO: APK não foi gerado em $APK_SRC"
  exit 4
fi

python3 "$ROOT/VALIDAR_APK_CLIENTE.py" "$APK_SRC"

mkdir -p "$(dirname "$SERVER_APK")"
cp -f "$APK_SRC" "$SERVER_APK"
chmod 644 "$SERVER_APK" 2>/dev/null || true

cp -f "$APK_SRC" "$ROOT/BRECHORISEE_CLIENTE.apk" 2>/dev/null || true

echo "OK: APK Cliente assinado/validado e publicado em:"
echo "$SERVER_APK"
ls -lh "$SERVER_APK"
