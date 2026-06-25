# BRECHORISEE v4.8.7 — Revisão do fluxo da cliente e APK

## Fluxo corrigido

A cliente não entra mais na live automaticamente após login, cadastro ou redefinição de senha.

Fluxo novo:

1. Cliente abre `/cliente` ou o app Android.
2. Faz login/cadastro.
3. O sistema redireciona para `/cliente/inicio`.
4. A tela inicial mostra botões: `Entrar na live`, `Ver vitrine`, `Minha sacola`, `Entregas`, `Chat`, `Minha conta`.
5. A live só abre quando a cliente toca em `Entrar na live`.

Mesmo que uma URL antiga mande `next=/cliente/live`, o backend sanitiza o destino e envia para `/cliente/inicio`.

## APK Cliente

O projeto Android foi ajustado para abrir `/cliente` como tela inicial, não `/app/cliente`.

Alterações:
- `DEFAULT_URL` agora aponta para `/cliente`.
- Setup inicial salva servidor como `/cliente`.
- Deep link `brechorisee://live-companion` abre `/cliente/live-companion`.
- `versionCode`: 11.
- `versionName`: `4.8.7-fluxo-cliente-apk-build`.

## Compilação do APK

Este pacote contém os fontes corrigidos, mas o APK precisa ser compilado em ambiente com Android SDK/Gradle.

Scripts adicionados:
- `COMPILAR_APK_CLIENTE_E_PUBLICAR.sh`
- `COMPILAR_APK_CLIENTE_E_PUBLICAR_WINDOWS.bat`

Depois de compilar, o APK válido é publicado em:

`BRECHORISEE_SERVIDOR/app/brechorisee_app/static/downloads/BRECHORISEE_CLIENTE.apk`

## Observação

Se o Android acusar erro ao instalar por cima de uma versão antiga, desinstale o app BRECHORISEE Cliente anterior e instale novamente. Isso pode acontecer quando o APK antigo foi assinado com outra chave.
