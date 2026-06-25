# Correção v4.8.8 — Bloqueio de APK antigo/incompatível

## Problema
O APK antigo instalava, mas fechava ao abrir com:

`ClassNotFoundException: com.brechorisee.cliente.MainActivity`

Isso indica que o APK publicado no site era de uma versão anterior/incompatível ou foi compilado sem a Activity principal esperada.

## Correção
- O servidor não libera mais download de APK que não tenha `com.brechorisee.cliente.MainActivity` dentro dos `classes*.dex`.
- O instalador Termux não preserva/publica APK antigo que falhe nessa validação.
- O script `PUBLICAR_APK_CLIENTE_BRECHORISEE.sh` agora rejeita APK antigo/incompatível.
- Adicionado `REMOVER_APK_CLIENTE_ANTIGO_TERMUX.sh` para limpar imediatamente o APK antigo do servidor.
- Projeto Android Cliente atualizado para `versionCode 12` e `versionName 4.8.8-bloqueio-apk-antigo`.

## Fluxo correto
1. Instalar o pacote v4.8.8 no Termux.
2. Usar o sistema pelo navegador enquanto o APK novo não for compilado.
3. Compilar o app Android Cliente pelo Android Studio/Gradle.
4. Copiar `BRECHORISEE_CLIENTE.apk` novo para Downloads do celular.
5. Rodar `bash ~/PUBLICAR_APK_CLIENTE_BRECHORISEE.sh`.

