#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

echo "=============================================="
echo " BRECHORISEE CLIENTE - GOOGLE PLAY AAB"
echo "=============================================="
echo

if ! command -v java >/dev/null 2>&1; then
  echo "ERRO: Java/JDK 17 ou superior não encontrado."
  exit 1
fi

GRADLE_BIN=""
if [ -x "./tools/gradle-8.10.2/bin/gradle" ]; then
  GRADLE_BIN="./tools/gradle-8.10.2/bin/gradle"
elif command -v gradle >/dev/null 2>&1; then
  GRADLE_BIN="$(command -v gradle)"
else
  echo "ERRO: Gradle não encontrado. Rode o script de APK no Windows ou instale Gradle."
  exit 1
fi

export ANDROID_SDK_ROOT="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-$HOME/Android/Sdk}}"
export ANDROID_HOME="$ANDROID_SDK_ROOT"
printf "sdk.dir=%s\n" "$ANDROID_SDK_ROOT" > local.properties

UPLOAD_DIR="play_store_upload"
KEYSTORE="$UPLOAD_DIR/brechorisee_upload.jks"
KEY_ALIAS="brechorisee_upload"
mkdir -p "$UPLOAD_DIR"

if [ ! -f "$KEYSTORE" ]; then
  echo "Nenhuma chave de upload encontrada."
  echo "Será criada uma nova chave local. Guarde play_store_upload em local seguro."
  read -r -s -p "Digite uma senha forte para a chave, mínimo 6 caracteres: " STORE_PASS
  echo
  if [ -z "$STORE_PASS" ]; then
    echo "Senha vazia não permitida."
    exit 1
  fi
  KEY_PASS="$STORE_PASS"
  keytool -genkeypair -v -keystore "$KEYSTORE" -alias "$KEY_ALIAS" -keyalg RSA -keysize 2048 -validity 10000 -storepass "$STORE_PASS" -keypass "$KEY_PASS" -dname "CN=BRECHORISEE Cliente,O=BRECHORISEE,L=Sao Paulo,ST=SP,C=BR"
else
  echo "Chave encontrada: $KEYSTORE"
  read -r -s -p "Digite a senha da chave de upload: " STORE_PASS
  echo
  KEY_PASS="$STORE_PASS"
fi

cat > keystore.properties <<EOF
storeFile=play_store_upload/brechorisee_upload.jks
storePassword=$STORE_PASS
keyAlias=$KEY_ALIAS
keyPassword=$KEY_PASS
EOF

"$GRADLE_BIN" --no-daemon clean bundleRelease

AAB_SRC="app/build/outputs/bundle/release/app-release.aab"
AAB_DST="BRECHORISEE_CLIENTE_GOOGLE_PLAY.aab"
cp "$AAB_SRC" "$AAB_DST"

echo
echo "AAB gerado com sucesso:"
echo "$(pwd)/$AAB_DST"
echo
echo "SHA-256 da chave de upload para assetlinks.json:"
keytool -list -v -keystore "$KEYSTORE" -alias "$KEY_ALIAS" -storepass "$STORE_PASS" | grep SHA256 || true
echo
echo "Coloque no Render:"
echo "BRECHORISEE_ANDROID_SHA256_FINGERPRINTS=COLE_AQUI"
