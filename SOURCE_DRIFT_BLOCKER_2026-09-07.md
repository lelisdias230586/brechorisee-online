# Bloqueador — drift entre GitHub `main` e produção

## Evidência

O `main` do repositório ainda contém versões antigas de telas críticas:

- `templates/online_order.html`: fluxo baseado em WhatsApp e botão `Pagar no cartão`.
- `templates/online_cart.html`: campos manuais de Pix e link InfinitePay/cartão.
- `templates/partials/product_card.html`: card sem a galeria/carrossel exibida atualmente no runtime.

A produção validada em 2026-09-07 já usa fluxo InfinitePay automático e UI diferente.

## Consequência

Nenhum patch visual sobre templates/CSS compartilhados deve ser tratado como candidato de produção antes de obter um snapshot somente leitura da árvore atual do Poco F3/Termux.

## Não autorizado por este documento

- deploy;
- restart/reload;
- mudança de DB;
- Caddy;
- watchdog;
- router;
- 8010;
- nova chamada à InfinitePay;
- webhook manual;
- `payment_check` manual;
- refund.
