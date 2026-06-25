#!/data/data/com.termux/files/usr/bin/bash
set -u
URL="${1:-}"
APP_DIR="$HOME/brechorisee-servidor/app"
ENV_FILE="$APP_DIR/.env"
if [ -z "$URL" ]; then
  echo "Uso:"
  echo "bash CONFIGURAR_LINK_PUBLICO_BRECHORISEE.sh https://LINK-REAL-QUE-APARECEU.lhr.life"
  echo "ou, depois de instalado:"
  echo "bash ~/CONFIGURAR_LINK_PUBLICO_BRECHORISEE.sh https://LINK-REAL-QUE-APARECEU.lhr.life"
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
