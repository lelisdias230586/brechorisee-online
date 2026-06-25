# BRECHORISEE v4.8.12 - BAT completo Windows

Esta versão atualiza o processo `FAZER_TUDO_BRECHORISEE_WINDOWS.bat`.

## O que o BAT faz agora

1. Compila o APK Cliente em release assinado.
2. Valida o APK Cliente com:
   - AndroidManifest.xml
   - classes.dex
   - assinatura válida por apksigner/META-INF
   - `com.brechorisee.cliente.MainActivity`
3. Publica o APK Cliente no servidor para download pelo site.
4. Compila o APK Admin em release assinado.
5. Valida o APK Admin com:
   - AndroidManifest.xml
   - classes.dex
   - assinatura válida por apksigner/META-INF
   - `com.brechorisee.admin.MainActivity`
6. Cria `PACOTE_TERMUX_MINI`.
7. Cria `PACOTE_TERMUX_MINI.zip`.
8. Cria `SISTEMA_BRECHORISEE_WINDOWS`.
9. Cria `SISTEMA_BRECHORISEE_WINDOWS.zip`.

## Arquivos principais

- `FAZER_TUDO_BRECHORISEE_WINDOWS.bat`
- `FAZER_TUDO_COMPLETO_BRECHORISEE_WINDOWS.bat`
- `BRECHORISEE_ADMIN/android/GERAR_APK_RELEASE_ASSINADO_WINDOWS.bat`
- `BRECHORISEE_ADMIN/android/VALIDAR_APK_ADMIN_WINDOWS.ps1`
- `BRECHORISEE_CLIENTE/android/GERAR_APK_RELEASE_ASSINADO_WINDOWS.bat`

## Saídas geradas no Windows

- `BRECHORISEE_CLIENTE.apk`
- `BRECHORISEE_ADMIN.apk`
- `PACOTE_TERMUX_MINI/`
- `PACOTE_TERMUX_MINI.zip`
- `SISTEMA_BRECHORISEE_WINDOWS/`
- `SISTEMA_BRECHORISEE_WINDOWS.zip`

## Observação

Não use `app-release-unsigned.apk`, `.aab` ou APK antigo. Use somente os APKs gerados na raiz pelo BAT.
