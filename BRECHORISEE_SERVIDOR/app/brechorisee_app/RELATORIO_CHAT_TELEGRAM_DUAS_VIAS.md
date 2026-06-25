# Correção Chat BRECHORISEE ↔ Telegram

Implementado em 18/06/2026.

## O que foi feito

- O Chat BRECHORISEE agora envia notificação ao Telegram com comando pronto para resposta.
- A atendente pode responder pelo Telegram usando:
  - `/responder ID mensagem`
  - `/r ID mensagem`
- A resposta do Telegram é gravada em `chat_messages` como mensagem de admin.
- A resposta aparece no chat da cliente no site/app.
- Quando a atendente responde pelo Telegram, o bot é pausado automaticamente naquela conversa para não disputar atendimento.
- Novo comando `/chats` lista as últimas conversas com IDs para resposta.
- O menu `/comandos` foi atualizado com os comandos do Chat BRECHORISEE.

## Exemplo de uso

Cliente envia no app/site:

```text
Gostei de uma blusa que vi ontem
```

Telegram recebe uma notificação com:

```text
Responder pelo Telegram: /responder 12 sua mensagem
Atalho: /r 12 sua mensagem
```

Atendente responde no Telegram:

```text
/responder 12 Claro Amanda, vou verificar essa blusa para você.
```

O sistema grava a resposta no Chat BRECHORISEE e a cliente vê a mensagem.

## Variáveis necessárias no Render

```env
TELEGRAM_BOT_TOKEN=...
TELEGRAM_ADMIN_CHAT_ID=...
TELEGRAM_ALLOWED_CHAT_IDS=...
TELEGRAM_WEBHOOK_SECRET=...
BRECHORISEE_TELEGRAM_SEND_REAL=1
BRECHORISEE_TELEGRAM_COMMANDS_ENABLED=1
PUBLIC_BASE_URL=https://brechorisee-online.onrender.com
```

## Webhook do Telegram

A URL do webhook deve apontar para:

```text
https://brechorisee-online.onrender.com/api/telegram/webhook?secret=SEU_TELEGRAM_WEBHOOK_SECRET
```

## Testes locais

- `app.py` compilou sem erro de sintaxe.
- Import do FastAPI OK.
- Comando `/chats` testado.
- Comando `/responder ID mensagem` testado.
- Mensagem foi inserida em `chat_messages` como `sender_type='admin'`.
- Metadata salva com origem `telegram`.
