# Patch status — InfinitePay redirect reconciliation

Branch: `fix/infinitepay-redirect-reconcile-2026-09-07`

## Estado

`PATCH_IMPLEMENTATION=BLOCKED_WAITING_CURRENT_RUNTIME_SOURCE`

O branch foi criado para a correção financeira aprovada em 2026-09-07. Neste momento ele NÃO contém alteração funcional porque o repositório `main` está defasado em relação ao runtime de produção cujo `app.py` operacional possui SHA:

`16e10fe03198d00a588b0b2206f6f6fc313355413555c63e2438a220dcf26c6b`

## Escopo autorizado nesta etapa

Preparar a correção do fallback:

`redirect_url -> payment_check server-to-server -> mesmo finalizador idempotente do webhook`

Sem deploy em produção.

## Não autorizado

- quarto pagamento real
- novo checkout
- refund
- correção manual do banco
- `payment_check` manual do pedido 28
- mudança de Caddy/watchdog/router/8010
- restart de produção
- marcar pedido como pago a partir de query params

## Condição para implementação

Sincronizar para este repositório a árvore atual do runtime do F3, no mínimo:

- `app/brechorisee_app/app.py`
- `app/brechorisee_app/templates/online_order.html`
- CSS/JS compartilhados tocados pelo fluxo do pedido, se houver

Somente depois aplicar patch e testes em branch; deploy continua exigindo autorização separada.
