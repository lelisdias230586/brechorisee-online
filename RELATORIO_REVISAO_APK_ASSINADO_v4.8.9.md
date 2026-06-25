# RELATÓRIO v4.8.9 — revisão completa do APK Cliente e publicação

## Problema confirmado

O erro no Android:

> Como o pacote parece ser inválido, o app não foi instalado.

acontece quando o arquivo `.apk` servido pelo site não é um APK Android instalável. No fluxo anterior, um APK podia passar pela validação básica porque tinha `AndroidManifest.xml` e `classes.dex`, mas ainda assim ser recusado pelo Android por estar **sem assinatura/certificado**, normalmente quando o arquivo usado era `app-release-unsigned.apk`.

Também foi mantida a correção do erro antigo:

> ClassNotFoundException: com.brechorisee.cliente.MainActivity

## Correções aplicadas

1. O servidor agora bloqueia APK sem assinatura.
2. O Termux não publica mais APK sem assinatura.
3. O script de publicação no Termux valida:
   - arquivo ZIP/APK válido;
   - `AndroidManifest.xml`;
   - `classes.dex`;
   - certificado em `META-INF/*.RSA`, `META-INF/*.DSA` ou `META-INF/*.EC`;
   - presença de `com.brechorisee.cliente.MainActivity` no DEX.
4. O projeto Android Cliente foi atualizado para:
   - `versionCode 13`;
   - `versionName 4.8.9-apk-assinado-validado`;
   - `MainActivity` declarada com nome completo no Manifest;
   - assinatura v1/v2/v3 habilitada no release.
5. O app Cliente abre em `/cliente/inicio`, evitando entrada direta na live.
6. Adicionado script principal para Windows:
   - `GERAR_APK_CLIENTE_FINAL_WINDOWS.bat`

## Script correto para compilar

No Windows, use somente:

```bat
GERAR_APK_CLIENTE_FINAL_WINDOWS.bat
```

Ele gera e publica automaticamente:

```text
BRECHORISEE_CLIENTE.apk
BRECHORISEE_SERVIDOR\app\brechorisee_app\static\downloads\BRECHORISEE_CLIENTE.apk
PACOTE_TERMUX_MINI\BRECHORISEE_CLIENTE.apk
```

## Não usar

Não use estes arquivos para instalar ou publicar:

```text
app-release-unsigned.apk
app-release.aab
qualquer .zip renomeado para .apk
APK antigo salvo no celular
APK antigo salvo no servidor Termux
```

## Instalação no Termux com pacote pequeno

Copie para o celular somente a pasta:

```text
PACOTE_TERMUX_MINI
```

Depois no Termux:

```bash
cd /sdcard/Download/PACOTE_TERMUX_MINI
bash SISTEMA_BRECHORISEE_CELULAR.sh
```

## Atualizar só o APK no servidor

Copie o APK final para Downloads do celular com este nome:

```text
BRECHORISEE_CLIENTE.apk
```

Depois rode:

```bash
bash ~/PUBLICAR_APK_CLIENTE_BRECHORISEE.sh
```

Se o APK não for assinado ou estiver errado, o script vai bloquear e mostrar o motivo.
