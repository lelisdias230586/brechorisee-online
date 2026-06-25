# BRECHORISEE Cliente — pacote preparado para Google Play

Esta pasta contém o material para publicar o app **BRECHORISEE Cliente** no Google Play Console.

## Arquivo do app

O Google Play pede **AAB**. Para gerar:

Windows:

```bat
brechorisee_cliente_android\GERAR_AAB_GOOGLE_PLAY_WINDOWS.bat
```

Linux/macOS:

```bash
cd brechorisee_cliente_android
./gerar_aab_google_play_linux_mac.sh
```

O arquivo final será:

```txt
brechorisee_cliente_android/BRECHORISEE_CLIENTE_GOOGLE_PLAY.aab
```

## Importante sobre a chave de upload

O script cria uma chave local em:

```txt
brechorisee_cliente_android/play_store_upload/brechorisee_upload.jks
```

Guarde essa pasta fora do projeto também, em backup seguro. Não envie para GitHub, ZIP público ou chat.

## App que deve ir para Play Store

Publicar primeiro:

```txt
Nome: BRECHORISEE Cliente
Pacote: com.brechorisee.cliente
Tipo: App público
Categoria sugerida: Compras
```

O app admin deve ficar privado/teste interno/instalação manual.

## Links públicos já preparados

Após subir esta versão no Render:

```txt
https://brechorisee-online.onrender.com/privacidade
https://brechorisee-online.onrender.com/termos
https://brechorisee-online.onrender.com/excluir-dados
https://brechorisee-online.onrender.com/suporte
https://brechorisee-online.onrender.com/cliente/tutorial
https://brechorisee-online.onrender.com/.well-known/assetlinks.json
```

## Depois de gerar o AAB

Rode:

```bat
brechorisee_cliente_android\MOSTRAR_SHA256_GOOGLE_PLAY_WINDOWS.bat
```

Copie o SHA-256 e coloque no Render:

```env
BRECHORISEE_ANDROID_PACKAGE_NAME=com.brechorisee.cliente
BRECHORISEE_ANDROID_SHA256_FINGERPRINTS=COLE_O_SHA256_AQUI
```

Isso ajuda os links `https://brechorisee-online.onrender.com/...` a abrirem direto no app.

## Arquivos de loja

Use os arquivos desta pasta:

```txt
google_play/PLAY_STORE_LISTAGEM.md
google_play/SEGURANCA_DOS_DADOS.md
google_play/PERMISSOES_E_DECLARACOES.md
google_play/NOTAS_DA_VERSAO.txt
google_play/assets/icon_512x512.png
google_play/assets/feature_graphic_1024x500.png
google_play/assets/screenshots/*.png
```

## Variáveis recomendadas no Render

```env
PUBLIC_BASE_URL=https://brechorisee-online.onrender.com
BRECHORISEE_VERSION=3.4-google-play-ready
BRECHORISEE_SUPPORT_EMAIL=suporte@brechorisee.com.br
BRECHORISEE_STORE_LEGAL_NAME=BRECHORISEE
BRECHORISEE_ANDROID_PACKAGE_NAME=com.brechorisee.cliente
BRECHORISEE_ANDROID_SHA256_FINGERPRINTS=COLE_O_SHA256_AQUI
BRECHORISEE_ANDROID_APP_URL=LINK_DA_PLAY_STORE_QUANDO_PUBLICAR
BRECHORISEE_CLIENT_APP_URL=LINK_DA_PLAY_STORE_QUANDO_PUBLICAR
```

## Ordem recomendada

1. Subir esta versão para GitHub.
2. Fazer deploy no Render.
3. Conferir `/privacidade`, `/termos`, `/excluir-dados`, `/suporte`.
4. Gerar o AAB.
5. Criar app no Play Console.
6. Preencher listagem, segurança dos dados e permissões.
7. Subir em **Teste interno**.
8. Instalar pela Play Store de teste e validar live, overlay, reserva, carrinho e tutorial.
9. Enviar para produção.
