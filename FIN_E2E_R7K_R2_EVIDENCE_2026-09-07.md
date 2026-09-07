# FIN-E2E R7K-R2 — evidência e desenho do fallback seguro

Data: 2026-09-07

## Escopo

Somente documentação/preparação. Nenhum deploy, chamada à InfinitePay, `payment_check`, alteração de banco, Caddy, watchdog, router, 8010 ou restart é autorizado por este arquivo.

## Evidência R7K-R2

Pedido alvo:

- order id: 28
- order code: `ONLINE-2609070932-273`
- order NSU: `BRECHORISEE-28`
- total: R$ 1,00

Estado atual do banco:

- `status=aguardando_pagamento`
- `payment_status=pendente`
- `payment_confirmed_by=NULL`
- `infinitepay_transaction_nsu=NULL`
- `infinitepay_invoice_slug=NULL`
- `updated_at=2026-09-07 09:34:54`

Probes do endpoint `/api/webhooks/infinitepay`:

1. backend direto `127.0.0.1:8000` → HTTP 400 esperado, `Webhook sem conteúdo.`
2. Caddy local TLS `brechorisee.duckdns.org:8443` via resolve local → HTTP 400 esperado
3. hostname público a partir do próprio F3 → HTTP 400 esperado

Conclusão: rota FastAPI e passagem pelo Caddy estão funcionais. O webhook real da transação não foi observado nos logs.

## Retorno real do provedor já observado

O redirect de volta ao pedido chegou com:

- `capture_method=credit_card`
- `transaction_id` presente
- `transaction_nsu` presente
- `slug` presente
- `order_nsu=BRECHORISEE-28`
- `receipt_url` presente

Esses parâmetros NÃO devem, por si só, marcar pedido como pago.

## Desenho recomendado

Adicionar um fallback idempotente no GET público do pedido.

Fluxo desejado:

```text
GET /loja/pedido/{token}
  -> carregar pedido pelo token público
  -> detectar query params order_nsu + transaction_nsu + slug
  -> validar sintaxe/tamanho e vínculo com o pedido carregado
  -> se pedido já confirmado com a mesma transação: retornar página normalmente (idempotente)
  -> se pedido terminal/conflitante ou NSU divergente: NÃO confirmar; registrar/retornar estado seguro
  -> chamar server-to-server payment_check
  -> exigir HTTP 2xx
  -> exigir success=true
  -> exigir paid=true
  -> exigir amount == total do pedido em centavos
  -> validar order_nsu / transaction_nsu / slug retornados quando presentes
  -> reutilizar EXATAMENTE o mesmo finalizador transacional/idempotente do webhook
  -> somente então persistir status pago/confirmado
  -> renderizar página atualizada
```

## Regra central

Nunca executar:

```text
query string -> UPDATE status='pago'
```

A única autoridade financeira continua sendo `payment_check` server-to-server.

## Reuso obrigatório

Não duplicar a lógica de finalização financeira. Extrair/reusar uma função interna comum para:

- webhook InfinitePay
- fallback da redirect URL

A função comum deve receber identidade já validada e resultado verificado do provider e executar a mesma seção crítica de:

- idempotência de transaction_nsu
- conflito de identidade
- vínculo transaction_nsu/invoice_slug
- sincronização Live/hold quando aplicável
- confirmação `payment_status='confirmado'`
- `payment_confirmed_by='infinitepay'`
- finalização comercial idempotente

## Segurança do GET público

O GET do pedido pode provocar uma verificação server-to-server apenas quando TODAS as condições abaixo forem verdadeiras:

- token público do pedido válido
- `order_nsu` presente e exatamente igual ao NSU já congelado no pedido
- `transaction_nsu` presente e sintaticamente válido
- `slug` presente e sintaticamente válido
- pedido não está cancelado/conflito terminal incompatível
- nenhum outro pedido usa a mesma `transaction_nsu`

Parâmetros como `receipt_url`, `capture_method` e `transaction_id` são informativos e não autorizam confirmação.

## Idempotência

Recarregar a redirect URL várias vezes deve ser seguro:

- nunca criar novo checkout
- nunca duplicar venda
- nunca duplicar vínculo de transaction_nsu
- nunca rebaixar pedido já confirmado
- nunca aceitar transaction_nsu diferente para pedido já vinculado

## Falhas

Se `payment_check` falhar, responder/renderizar o pedido como pendente, sem alterar status financeiro.

Falhas ambíguas de rede não devem gerar retry em loop dentro do request. Uma nova navegação pode tentar novamente de forma idempotente, desde que os mesmos identificadores estejam presentes.

## Observabilidade recomendada

Registrar evento sem segredos, por exemplo:

- `infinitepay_redirect_reconcile_started`
- `infinitepay_redirect_reconcile_verified`
- `infinitepay_redirect_reconcile_pending`
- `infinitepay_redirect_reconcile_conflict`
- `infinitepay_redirect_reconcile_error`

Não registrar token público completo, receipt_url completo ou credenciais.

## Testes obrigatórios antes de deploy

1. redirect sem parâmetros → nenhuma chamada provider
2. parâmetros incompletos → nenhuma chamada provider
3. order_nsu divergente → bloqueia
4. transaction_nsu duplicado em outro pedido → bloqueia
5. payment_check HTTP não 2xx → mantém pendente
6. success=false → mantém pendente
7. paid=false → mantém pendente
8. amount divergente → conflito/bloqueio conforme regra existente
9. identidade provider divergente → conflito terminal conforme regra existente
10. sucesso realista → confirma uma única vez
11. reload da mesma URL → idempotente
12. webhook depois do fallback → idempotente
13. fallback depois do webhook → idempotente
14. nenhuma regressão em checkout `/links`
15. nenhuma regressão em pedidos antigos pendentes

## Bloqueador atual

O branch ainda NÃO contém o snapshot atual do runtime de produção. O `main` do GitHub está defasado. Portanto, este documento não é patch aplicável; é especificação para ser implementada somente após sincronização da árvore atual do F3.
