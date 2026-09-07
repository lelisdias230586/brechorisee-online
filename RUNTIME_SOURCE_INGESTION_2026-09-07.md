# Ingestão do snapshot de runtime — 2026-09-07

## Archive recebido

`BRECHORISEE_RUNTIME_SOURCE_SNAPSHOT_20260907_133607.tar.gz`

SHA-256 verificado independentemente:

`6d93c302f79f56193ec58f6cd8e4ed57e2b73176c5dbfa0bfcffc18863faaf9f`

## Segurança da extração

- paths absolutos: 0
- path traversal (`..`): 0
- symlinks: 0
- hardlinks: 0
- arquivos no archive: 114

Resultado: `SAFE_EXTRACTION=PASS`.

## Manifesto

O `SHA256SUMS.txt` contém 114 entradas. A primeira é autorreferente e registra o hash do arquivo ainda vazio (`e3b0...`) porque o shell abriu/redirecionou o manifesto antes de o `find`/`sha256sum` percorrê-lo.

Excluindo somente a linha do próprio `SHA256SUMS.txt`:

- arquivos-fonte verificados: 113
- divergências: 0

Resultado: `SOURCE_FILES_MANIFEST=PASS_113_OF_113`.

Classificação da linha autorreferente: `KNOWN_HARNESS_DEFECT`, não corrupção de fonte.

## app.py operacional

- tamanho: 1.510.403 bytes
- SHA-256: `16e10fe03198d00a588b0b2206f6f6fc313355413555c63e2438a220dcf26c6b`

Coincide exatamente com o SHA congelado em produção.

## Drift do GitHub main

O `main` continua significativamente defasado em relação a este snapshot. Portanto patches preparados para o runtime atual não devem ser aplicados sobre os templates/app.py antigos do `main` sem um passo explícito de sincronização/rebase.

## Correção de falso positivo da auditoria antiga

O defeito observado anteriormente em `sale_detail.html` no `main` antigo (bloco de entrega dentro de `page_title` e repetido em `content`) NÃO está presente no snapshot atual do runtime. Deve ser classificado como drift do `main`, não como bug atual de produção.

## Limitação do snapshot

O pacote solicitado continha `app.py`, `templates/`, `static/css/` e `static/js/`, mas não os módulos Python locais importados por `app.py` (`live_checkout_v3`, `payment_provider_adapter_v6`, entre outros). Assim, compilação sintática do `app.py` é possível, mas startup/import integral da aplicação exige snapshot adicional desses módulos.

## Produção

Nenhum arquivo deste snapshot foi implantado ou alterado no servidor durante a ingestão.