# Telegram interno + revisão do .env

Esta versão adiciona o Telegram como central interna da equipe para a live, pedidos e pagamentos.

## O que foi implementado

- Carregamento automático de `.env` pelo próprio `app.py`, sem depender de `python-dotenv`.
- Leitura de `.env` em `brechorisee_app/.env` e também no `.env` da raiz do ZIP.
- Página administrativa `/telegram`.
- API `/api/telegram/status`, `/api/telegram/test`, `/api/telegram/control` e `/api/telegram/webhook`.
- Controle de segurança por `TELEGRAM_WEBHOOK_SECRET` e `TELEGRAM_ALLOWED_CHAT_IDS`.
- Modo seguro/simulado por padrão: `BRECHORISEE_TELEGRAM_SEND_REAL=0`.
- Alertas internos no Telegram para:
  - peça adicionada à fila;
  - próxima peça mostrada;
  - reserva principal;
  - fila de espera;
  - comentário com intenção de compra;
  - pagamento/Pix confirmado;
  - peça vendida;
  - reserva cancelada e promoção da próxima cliente.

## Comandos úteis no Telegram

Durante a live:

- `/painel` — resumo da Central da Live.
- `/atual` — peça atual com preço, tamanho, medidas e link público.
- `/fila` — lista de peças da fila.
- `/proxima` — mostra a próxima peça da fila.
- `/addfila BLUSA-023` — adiciona uma peça à fila pelo código ou nome.
- `/reservar Maria | 11999999999` — reserva a peça atual para Maria.
- `/espera Ana` — coloca Ana direto na fila de espera.
- `/vendida` — marca a peça atual como vendida.
- `/pago Maria` — confirma pagamento das reservas pendentes da cliente na live.
- `/carrinho Maria` — gera resumo e link do carrinho da live.
- `/resumo_live` — relatório rápido da live e link da repescagem.

Pedidos online já existentes:

- `/pedido ID` — detalhes do pedido.
- `/pedido ID pago` — confirma pagamento.
- `/pedido ID cancelar` — cancela pedido.
- `/pedido ID entrega` — marca como em entrega.
- `/pedido ID entregue` — marca como entregue.
- `/cliente TELEFONE` — busca cliente/pedidos.

## Como ativar

1. Copie `.env.example` para `.env`.
2. Preencha:
   - `PUBLIC_BASE_URL`
   - `BRECHORISEE_SECRET_KEY`
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_ADMIN_CHAT_ID`
   - `TELEGRAM_WEBHOOK_SECRET`
3. Deixe `BRECHORISEE_TELEGRAM_SEND_REAL=0` para testar em modo simulado.
4. Abra `/telegram` e use o teste de comando.
5. Quando estiver tudo certo, troque para `BRECHORISEE_TELEGRAM_SEND_REAL=1`.

## Webhook

Configure o webhook do Telegram apontando para:

```text
https://SEU-DOMINIO.com/api/telegram/webhook?secret=SEU_TELEGRAM_WEBHOOK_SECRET
```

Também é possível enviar o segredo pelo header oficial `x-telegram-bot-api-secret-token`.

## Segurança

- Não coloque token real dentro de ZIP compartilhado.
- Use `TELEGRAM_ALLOWED_CHAT_IDS` para limitar quem pode dar comandos.
- Se `TELEGRAM_ALLOWED_CHAT_IDS` ficar vazio, o sistema usa `TELEGRAM_ADMIN_CHAT_ID` como chat permitido.
- Se quiser desligar comandos sem remover o bot, use:

```text
BRECHORISEE_TELEGRAM_COMMANDS_ENABLED=0
```

## Arquivos revisados

- `.env.example`
- `brechorisee_app/.env.example`
- `brechorisee_app/app.py`
- `brechorisee_app/templates/base.html`
- `brechorisee_app/templates/telegram_admin.html`
