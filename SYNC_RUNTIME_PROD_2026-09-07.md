# Sincronização segura do runtime de produção — 2026-09-07

Este branch foi criado somente como destino de sincronização. Nenhum arquivo funcional foi alterado.

## Objetivo

Trazer para revisão a árvore atual de produção de templates/CSS/JS/app.py correspondente ao runtime validado no Poco F3/Termux, sem alterar o runtime e sem tocar banco, Caddy, watchdog, router, porta 8010 ou fluxo financeiro.

## Regra

Não copiar segredos, `.env`, banco SQLite, cookies, tokens ou credenciais. Somente código-fonte e assets de interface necessários para revisão.

## Evidência de drift

O `main` do GitHub está desatualizado em relação ao fluxo InfinitePay e às telas atuais. Por isso, este branch não deve receber patches funcionais até que a base de produção seja copiada para cá de forma somente leitura no servidor.

## Estado

`WAITING_FOR_RUNTIME_SOURCE_SNAPSHOT`
