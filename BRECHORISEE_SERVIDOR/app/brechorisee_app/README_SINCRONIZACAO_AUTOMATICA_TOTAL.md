# BRECHORISEE - Sincronização automática total

Esta versão sincroniza automaticamente Local ⇄ Nuvem ⇄ Android.

Regra:
- Cadastrou em qualquer lugar: aparece nos demais quando houver conexão.
- Vendeu em qualquer lugar: sai do estoque disponível nos demais quando sincronizar.
- Se a internet/nuvem estiver fora: fica na fila e envia automaticamente quando voltar.
- Status vendido tem prioridade para evitar revenda.
- O código da peça é a chave para não duplicar.

Configuração local:
- O servidor local usa CLOUD_SYNC_URL. Se não configurar, usa por padrão:
  https://brechorisee-online.onrender.com

Configuração no Render:
- Defina APP_ENV=production para a nuvem não tentar sincronizar com ela mesma.

Tela:
- /sincronizacao mostra status, pendências e conflitos.
- Não é necessário clicar em botão; a sincronização roda automaticamente.

Preserve ao atualizar:
- brechorisee_app/brechorisee.db
- brechorisee_app/static/uploads
- brechorisee_app/static/generated
- brechorisee_app/static/qrcodes
