# Banco de dados do BRECHORISEE

## O sistema roda sem `brechorisee.db`?

Sim. O backend usa SQLite e cria o arquivo automaticamente quando ele não existe.

O caminho padrão é:

```text
brechorisee_app/brechorisee.db
```

Mas em produção deve ser configurado por variável de ambiente:

```text
BRECHORISEE_DB_PATH=/var/data/brechorisee.db
```

## O que é criado automaticamente

Na inicialização, o app executa `init_db()` e cria as tabelas com `CREATE TABLE IF NOT EXISTS`. Em um banco novo, ele também cria dados mínimos:

- fornecedor padrão
- configurações básicas da loja
- opções padrão de atributos de peças
- usuário/PIN interno inicial do módulo profissional

A conta administrativa do portal é criada pelo fluxo de primeiro acesso em `/admin-acesso`.

## O que acontece se apagar o banco

O sistema sobe novamente, mas como banco novo. Isso significa que dados anteriores somem:

- produtos
- clientes
- pedidos
- vendas
- reservas
- histórico da live
- configurações alteradas
- contas criadas

Por isso o banco deve ser preservado no servidor.

## GitHub

Não envie banco real para o GitHub. O repositório deve guardar código e documentação; dados ficam no servidor, backup seguro ou volume persistente.

O `.gitignore` já bloqueia:

```text
*.db
*.sqlite
*.sqlite3
*.db-wal
*.db-shm
```

## Render

O `render.yaml` usa disco persistente em `/var/data` e define `BRECHORISEE_DB_PATH=/var/data/brechorisee.db`. Esse é o formato correto para o banco sobreviver a redeploys.


## Controle de versão do schema

O app registra uma versão lógica em `schema_migrations`. Isso não substitui uma ferramenta completa como Alembic, mas cria uma base segura para evoluir o banco sem depender de arquivos `.db` no GitHub.

Versão inicial deste pacote:

```text
2026_06_base_profissional
```

## Backup e restauração

Use:

```bash
python scripts/backup_dados_sqlite.py
python scripts/restaurar_backup_sqlite.py --help
```

Veja também:

```text
docs/BACKUP_E_RESTAURACAO.md
```
