# Patch status — InfinitePay redirect reconciliation

Branch: `fix/infinitepay-redirect-reconcile-2026-09-07`

## Estado

`LOCAL_PATCH_FROM_CURRENT_RUNTIME=READY`
`PRODUCTION_DEPLOY=NOT_AUTHORIZED`

O snapshot sanitizado do runtime do F3 foi recebido e validado.

Base operacional `app.py` SHA-256:

`16e10fe03198d00a588b0b2206f6f6fc313355413555c63e2438a220dcf26c6b`

Archive original SHA-256:

`6d93c302f79f56193ec58f6cd8e4ed57e2b73176c5dbfa0bfcffc18863faaf9f`

Validação: 113/113 arquivos-fonte do snapshot conferem com o manifesto quando se exclui a linha autorreferente do próprio `SHA256SUMS.txt` (defeito conhecido do harness de geração do manifesto, não corrupção de fonte).

## Patch preparado localmente

Fallback:

`redirect_url -> validação local -> failover write gate -> payment_check server-to-server -> mesmo núcleo transacional/idempotente do webhook`

O núcleo financeiro original do webhook foi extraído para um helper comum. Comparação AST confirmou equivalência do núcleo antigo com o novo helper, exceto pela parametrização intencional do `source_label`.

Regras mantidas:

- query params nunca marcam pedido como pago;
- `payment_check` é obrigatório;
- amount deve coincidir com o total congelado;
- transaction_nsu permanece único;
- divergência provider-verificada continua indo para conflito;
- repetição da mesma transação é idempotente;
- GET de redirect aplica explicitamente o failover write gate antes de qualquer efeito financeiro;
- GET financeiro não dispara a sincronização genérica pós-request;
- sucesso limpa os parâmetros financeiros da URL com redirect 303.

SHA-256 do patch textual local:

`d1f491b87cb16f7ede746053c784430bfc55313d77fa8f532f7c7ff472add7da`

## Testes locais

`PY_COMPILE=PASS`
`WEBHOOK_CORE_AST_EQUIVALENT_EXCEPT_SOURCE_LABEL_PARAM=PASS`
`FINANCIAL_HELPER_MOCK_MATRIX=PASS`
`REDIRECT_GUARD_MATRIX_WITH_FAILOVER=PASS`

Cobertos, entre outros:

- sem/incompletos parâmetros -> zero provider call;
- order_nsu divergente -> zero provider call;
- failover bloqueado -> zero provider call;
- paid=false -> mantém pendente;
- pagamento verificado -> pago/confirmado/infinitepay;
- reload mesma transação -> idempotente sem novo provider call;
- transaction_nsu duplicado -> bloqueio;
- amount/identidade provider divergentes -> conflito.

## Limitação do snapshot

O snapshot não incluiu os módulos Python locais importados por `app.py` (`live_checkout_v3`, `payment_provider_adapter_v6`, etc.). Por isso não foi executado startup integral do aplicativo neste ambiente. O arquivo completo passou compilação e os testes financeiros foram executados em SQLite temporário com stubs dos módulos externos/Live.

## Não autorizado

- deploy em produção;
- restart/reload;
- quarto pagamento real;
- novo checkout;
- refund;
- correção manual do banco;
- `payment_check` manual do pedido 28;
- mudança de Caddy/watchdog/router/8010;
- marcar pedido como pago a partir de query params.
