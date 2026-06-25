# Checklist antes de enviar para o Google Play

## Projeto

- [ ] Subir esta versão no GitHub.
- [ ] Deploy no Render sem erro.
- [ ] `PUBLIC_BASE_URL` configurado com domínio público.
- [ ] `/privacidade` abre sem login.
- [ ] `/termos` abre sem login.
- [ ] `/excluir-dados` abre sem login.
- [ ] `/suporte` abre sem login.
- [ ] `/cliente/tutorial` abre sem login.

## Android

- [ ] Rodar `GERAR_AAB_GOOGLE_PLAY_WINDOWS.bat`.
- [ ] Guardar backup de `play_store_upload/brechorisee_upload.jks`.
- [ ] Gerar `BRECHORISEE_CLIENTE_GOOGLE_PLAY.aab`.
- [ ] Rodar `MOSTRAR_SHA256_GOOGLE_PLAY_WINDOWS.bat`.
- [ ] Configurar `BRECHORISEE_ANDROID_SHA256_FINGERPRINTS` no Render.
- [ ] Fazer novo deploy após configurar SHA-256.
- [ ] Conferir `/.well-known/assetlinks.json`.

## Play Console

- [ ] Criar app BRECHORISEE Cliente.
- [ ] Enviar AAB em teste interno.
- [ ] Colocar descrição curta/completa.
- [ ] Enviar ícone 512x512.
- [ ] Enviar feature graphic 1024x500.
- [ ] Enviar screenshots.
- [ ] Preencher segurança dos dados.
- [ ] Preencher classificação indicativa.
- [ ] Preencher público-alvo.
- [ ] Declarar permissões sensíveis, especialmente sobreposição.
- [ ] Adicionar URL de privacidade.

## Teste interno

- [ ] Instalar pelo link da Play Store.
- [ ] Abrir tutorial.
- [ ] Permitir notificações.
- [ ] Iniciar live no admin.
- [ ] Confirmar notificação no cliente.
- [ ] Trocar peça no admin.
- [ ] Confirmar card dinâmico no cliente.
- [ ] Reservar peça pelo cliente.
- [ ] Ver reserva na Central da Live.
- [ ] Testar carrinho e WhatsApp.
