#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
echo "BRECHORISEE - compilar APK Android"
if ! command -v java >/dev/null 2>&1; then
  echo "Java/JDK 17 não encontrado."
  exit 1
fi
if ! command -v gradle >/dev/null 2>&1; then
  echo "Gradle não encontrado. No Linux/macOS, instale Gradle e Android SDK command-line tools ou use o .bat no Windows."
  exit 1
fi
: "${ANDROID_SDK_ROOT:=$HOME/Android/Sdk}"
export ANDROID_SDK_ROOT
export ANDROID_HOME="$ANDROID_SDK_ROOT"
printf "sdk.dir=%s\n" "$ANDROID_SDK_ROOT" > local.properties
gradle --no-daemon assembleDebug
cp app/build/outputs/apk/debug/app-debug.apk BRECHORISEE_android.apk
echo "APK gerado: $(pwd)/BRECHORISEE_android.apk"
