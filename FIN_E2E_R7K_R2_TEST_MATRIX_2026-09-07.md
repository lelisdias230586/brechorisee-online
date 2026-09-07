# Matriz de testes — fallback redirect → payment_check

Status: preparação; não é autorização de deploy.

| Caso | Entrada | Provider mock | Resultado esperado |
|---|---|---|---|
| F01 | GET pedido sem params | não chamado | render normal, sem mutação |
| F02 | só order_nsu | não chamado | render normal/aviso seguro, sem mutação |
| F03 | order_nsu divergente | não chamado | bloqueio seguro, sem mutação |
| F04 | transaction_nsu vazio | não chamado | sem mutação |
| F05 | slug vazio | não chamado | sem mutação |
| F06 | ids válidos | HTTP 500 | pendente, sem vínculo financeiro |
| F07 | ids válidos | HTTP 200 success=false | pendente |
| F08 | ids válidos | paid=false | pendente |
| F09 | ids válidos | amount divergente | conflito/bloqueio segundo regra existente |
| F10 | ids válidos | order_nsu divergente na resposta | conflito |
| F11 | ids válidos | transaction_nsu divergente na resposta | conflito |
| F12 | ids válidos | slug divergente na resposta | conflito |
| F13 | ids válidos | success=true, paid=true, amount correto | confirmar uma vez |
| F14 | reload mesma redirect | mesmo retorno pago | idempotente, zero venda duplicada |
| F15 | webhook após F13 | mesmo pagamento | idempotente |
| F16 | fallback após webhook confirmado | mesma identidade | idempotente |
| F17 | transaction_nsu já ligado a outro pedido | provider não deve finalizar | bloqueio |
| F18 | pedido cancelado/conflito terminal | provider não deve finalizar | bloqueio |
| F19 | pedido já confirmado, transaction igual | provider opcionalmente não chamado | render confirmado |
| F20 | pedido já confirmado, transaction diferente | não confirmar | conflito/bloqueio |

## Invariantes

- `query params` nunca confirmam pagamento diretamente.
- `payment_check` é obrigatório para transição financeira.
- `amount` validado em centavos contra o total congelado.
- nenhum caminho cria novo checkout.
- nenhum caminho chama `/links`.
- nenhuma falha rebaixa pedido confirmado.
- nenhuma repetição duplica venda.
- `transaction_nsu` permanece único.
- `payment_confirmed_by` final deve ser `infinitepay`.
- ordem final bem-sucedida deve terminar com `status='pago'` e `payment_status='confirmado'`.
