# UI P1 — patch sobre runtime atual

Branch: `fix/ui-p1-runtime-2026-09-07`

## Estado

`LOCAL_PATCH_FROM_CURRENT_RUNTIME=READY`
`PRODUCTION_DEPLOY=NOT_AUTHORIZED`

Base: snapshot sanitizado do F3 com `app.py` SHA-256 `16e10fe03198d00a588b0b2206f6f6fc313355413555c63e2438a220dcf26c6b`.

## Correções locais preparadas

1. Pedido InfinitePay: espaçamento explícito em `Toque em Pagar agora para abrir a InfinitePay`.
2. Prompt `Ativar avisos de pedidos`: removido do overlay fixo inferior e inserido no fluxo normal do Admin, eliminando cobertura de cards/formulários/previews.
3. Catálogo: empty-state cliente não aparece quando o servidor já renderizou `.brm-server-empty`, eliminando duplicidade.
4. Catálogo Admin mobile: CSS isolado para busca/microfone/filtro, tabs horizontais sem clipping, cabeçalho, cards e ações.
5. Imagens do catálogo Admin mobile: proporção 4:5 e foco superior para reduzir cortes ruins em peças de roupa.
6. Cache tokens dos JS alterados foram incrementados.

## Testes locais

- Jinja parse `base.html`: PASS
- Jinja parse `online_order.html`: PASS
- Jinja parse `products.html`: PASS
- `node --check admin-order-notifications.js`: PASS
- `node --check marketplace-vitrine-v1.js`: PASS
- `admin-products-mobile-v1.css` via tinycss2: PASS / 0 erros

SHA-256 do patch textual local:

`f3a91e8f778bcd6dff5f0d9feacb8a7682610c938bcb28932a8c330f424e895f`

## Não tratado como defeito do produto

Diálogos Google Play Protect/Android observados durante instalação do Live Observer são UI do sistema operacional e não entram neste patch.

## Deploy

Nenhum arquivo foi aplicado no F3 de produção. Deploy continua dependendo de autorização específica e gate de regressão.