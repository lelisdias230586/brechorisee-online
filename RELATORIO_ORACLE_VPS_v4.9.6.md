# RELATÓRIO — BRECHORISEE v4.9.6 Oracle VPS

## Objetivo

Preparar o BRECHORISEE para rodar em Oracle Cloud Free VPS como caminho principal de produção, sem Render e sem localhost.run.

## Arquivos adicionados

```text
CONFIGURAR_ORACLE_CLOUD_FREE_BRECHORISEE.md
BRECHORISEE_SERVIDOR/app/oracle-install.sh
BRECHORISEE_SERVIDOR/app/oracle-update-from-github.sh
BRECHORISEE_SERVIDOR/app/oracle-backup.sh
BRECHORISEE_SERVIDOR/app/.env.oracle.example
BRECHORISEE_SERVIDOR/app/oracle-nginx-brechorisee.conf
BRECHORISEE_SERVIDOR/app/oracle-brechorisee.service
SUBIR_PARA_GITHUB_ORACLE_WINDOWS.bat
SUBIR_PARA_GITHUB_ORACLE_WINDOWS.ps1
```

## O que o instalador faz

```text
1. Instala Python, Git, Nginx, Certbot, SQLite e dependências
2. Cria usuário brechorisee
3. Copia o sistema para /opt/brechorisee
4. Cria venv Python
5. Instala requirements.txt
6. Cria .env de produção
7. Usa banco persistente em /var/lib/brechorisee/brechorisee.db
8. Configura serviço systemd
9. Configura Nginx reverse proxy
10. Libera firewall Ubuntu nas portas 22, 80 e 443
11. Tenta configurar HTTPS quando DOMAIN for informado
```

## Comando principal

Sem domínio:

```bash
sudo PUBLIC_BASE_URL=http://IP-PUBLICO-DA-ORACLE ./oracle-install.sh
```

Com domínio:

```bash
sudo DOMAIN=app.seudominio.com.br PUBLIC_BASE_URL=https://app.seudominio.com.br ./oracle-install.sh
```

## Observação

Ainda será necessário liberar as portas 80 e 443 no painel da Oracle Cloud.
