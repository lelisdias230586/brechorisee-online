# BRECHORISEE R7M — auditoria de rotas duplicadas/sombreadas

Data: 2026-09-07

## Escopo

Auditoria e candidato local somente. Nenhum deploy, restart, alteração de banco, Caddy, provider ou pagamento real.

## Fonte

Base: candidato R7L + UI P1 + UI P2, derivado do snapshot operacional do F3 cujo `app.py` original possui SHA-256:

`16e10fe03198d00a588b0b2206f6f6fc313355413555c63e2438a220dcf26c6b`

## Achado

O aplicativo importado com stubs estritamente para os módulos ausentes no snapshot registrava:

- `418` rotas FastAPI/Starlette
- `20` chaves método+caminho duplicadas
- `21` registros excedentes, pois `/clie` aparecia três vezes

O teste dinâmico confirmou os handlers vencedores no objeto `app.routes`.

## Classificação

### Live — 7 registros antigos sombreados

Os handlers v5.11.29 são registrados antes dos equivalentes v5.11.25 e vencem:

- GET `/api/live/status`
- POST `/api/live/configurar`
- POST `/api/live/destacar`
- POST `/api/live/remover-destaque`
- POST `/api/live/reservar`
- GET `/api/live/reservas`
- GET `/limpar-cache`

O candidato R7M desabilita somente os decorators v5.11.25. As funções e middleware antigos permanecem definidos.

### Chat/vídeo — 4 registros repetidos

Os blocos duplicados têm corpo AST idêntico:

- GET `/chat/chamada/{thread_id}`
- GET `/api/chat/call/{thread_id}/signals`
- POST `/api/chat/call/{thread_id}/signals`
- POST `/api/chat/{thread_id}/video-invite`

O candidato desabilita apenas o segundo conjunto de decorators.

### Cliente / aliases — 9 registros excedentes

Rotas efetivas antes da limpeza:

- `/clie` → `redirect_clie`
- `/client` → `customer_portal_entry`
- `/clientes` → `customer_portal_entry`
- `/cliente` → `customer_portal_entry`
- `/cliente/login` → `customer_portal_entry`
- `/cliente/entrar` → `customer_portal_entry`
- `/login-cliente` → `customer_portal_entry`
- `/cliente/vitrine` → `customer_private_store`
- `/baixar-app` → `brechorisee_apps_download_page_v51110`

Os aliases v4.9.20 registrados depois eram sombreados. O decorator `/clie` dentro de `customer_portal_entry` também era sombreado pelo redirect anterior.

## Prova de invariância

```text
BEFORE_ROUTE_COUNT=418
BEFORE_DUP_KEYS=20
BEFORE_DUP_EXCESS=21

AFTER_ROUTE_COUNT=397
AFTER_DUP_KEYS=0
AFTER_DUP_EXCESS=0

WINNER_KEYSET_EQUAL=SIM
WINNER_METHOD_PATH_KEYS=397
WINNER_ENDPOINTS_CHANGED=0
```

Nenhuma chave método+caminho efetivamente atendida foi removida e nenhum handler vencedor mudou.

## OpenAPI

Antes da limpeza, o OpenAPI documentava alguns handlers sombreados em vez do handler que realmente atendia a requisição. Após R7M, os endpoints documentados passam a coincidir com os handlers vencedores para os casos auditados.

O warning restante `api_sync_failover_backup_api_sync_failover_backup_post` não é duplicidade de rota: uma única função usa `@app.api_route(..., methods=["GET", "POST"])`. Classificação separada P3 de documentação/OpenAPI.

## Testes

- Python compile: PASS
- Jinja parse: PASS 80/80
- JavaScript `node --check`: PASS 14/14
- CSS parse: PASS 9/9
- startup com stubs: PASS
- duplicidades método+caminho após patch: 0
- keyset preservado: PASS 397/397
- endpoint vencedor alterado: 0

## Segurança

O patch não toca InfinitePay, pedido 28, banco de produção, Caddy, watchdog, router/8010, autenticação financeira ou `.env`.

`ROUTE_SHADOW_CLEANUP_R7M=PASS_LOCAL_CANDIDATE`

`PRODUCTION_DEPLOY=NAO_AUTORIZADO`
