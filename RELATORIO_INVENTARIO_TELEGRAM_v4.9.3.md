# RELATÓRIO - BRECHORISEE v4.9.3

## Foco da versão
Inventário profissional por câmera/QR e controle pelo Telegram.

## Novas rotas
- `/inventario-profissional`
- `/inventario-profissional/relatorio/{session_id}`
- `/telegram`
- `/api/inventario-profissional/resumo`
- `/api/inventario-profissional/sessao`
- `/api/inventario-profissional/scan`
- `/api/inventario-profissional/ajustar-status`
- `/api/inventario-profissional/fechar`
- `/api/telegram/status`
- `/api/telegram/teste`
- `/api/telegram/enviar`
- `/api/telegram/avisar`
- `/api/telegram/eventos`
- `/api/telegram/webhook/configurar`
- `/telegram/webhook/{secret}`

## Inventário profissional
- Abre sessão de inventário.
- Lê QR/código pela câmera quando o navegador suporta `BarcodeDetector`.
- Permite digitação manual quando a câmera/leitor não suportar.
- Identifica peça pelo código ou título.
- Classifica leitura como:
  - `ok`
  - `nao_encontrada`
  - `duplicada`
  - `vendida_encontrada`
- Ajusta status da peça.
- Fecha sessão e gera relatório imprimível/salvável como PDF.
- Registra alertas para Telegram quando encontra divergência.

## Telegram
- Painel web em `/telegram`.
- Envio manual de avisos.
- Botões inline no Telegram para:
  - resumo
  - estoque
  - inventário
  - consignado
  - mensagens
  - live
- Webhook protegido por `TELEGRAM_WEBHOOK_SECRET`.
- Comandos:
  - `/start`
  - `/resumo`
  - `/estoque`
  - `/inventario`
  - `/live`
  - `/consignado`
  - `/mensagens`
  - `/ajuda`
- Dashboard com métricas e gráfico simples.

## .env
O `.env` enviado foi incorporado ao pacote para o servidor.  
Também foi criado `.env.example` com campos sensíveis removidos.

## Segurança
Não compartilhe publicamente:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_WEBHOOK_SECRET`
- `TELEGRAM_ADMIN_CHAT_ID`
- tokens internos do sistema

## Próxima versão sugerida
v4.9.4 - Consultor de estilo e sugestões inteligentes por cliente/família.
