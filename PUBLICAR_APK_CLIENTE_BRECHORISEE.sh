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
