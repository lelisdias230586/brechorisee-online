#!/usr/bin/env python3
# Validador de APK BRECHORISEE Cliente v4.8.9
# Uso: python VALIDAR_APK_CLIENTE.py caminho\BRECHORISEE_CLIENTE.apk

import os
import sys
import zipfile

def fail(msg: str) -> None:
    print("INVALIDO:", msg)
    sys.exit(1)

def main() -> None:
    if len(sys.argv) < 2:
        print("Uso: python VALIDAR_APK_CLIENTE.py BRECHORISEE_CLIENTE.apk")
        sys.exit(2)

    p = sys.argv[1]
    if not os.path.isfile(p):
        fail("arquivo nao encontrado")
    if os.path.getsize(p) < 16 * 1024:
        fail("arquivo muito pequeno para ser APK valido")
    if not zipfile.is_zipfile(p):
        fail("arquivo nao e ZIP/APK valido")

    with zipfile.ZipFile(p) as z:
        names = set(z.namelist())
        upper_names = {n.upper() for n in names}

        if "AndroidManifest.xml" not in names:
            fail("sem AndroidManifest.xml")
        dex_names = [n for n in names if n.startswith("classes") and n.endswith(".dex")]
        if not dex_names:
            fail("sem classes.dex")

        has_cert = any(
            n.startswith("META-INF/") and (n.endswith(".RSA") or n.endswith(".DSA") or n.endswith(".EC"))
            for n in upper_names
        )
        if not has_cert:
            fail("APK sem assinatura/certificado. Nao use app-release-unsigned.apk.")

        markers = (b"Lcom/brechorisee/cliente/MainActivity;", b"com/brechorisee/cliente/MainActivity")
        found = False
        for dex in dex_names:
            data = z.read(dex)
            if any(m in data for m in markers):
                found = True
                break
        if not found:
            fail("classes.dex nao contem com.brechorisee.cliente.MainActivity")

    print("OK: APK valido, assinado e compativel com BRECHORISEE Cliente.")
    print(os.path.abspath(p))
    print(f"Tamanho: {os.path.getsize(p)} bytes")

if __name__ == "__main__":
    main()
