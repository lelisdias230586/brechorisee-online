# BRECHORISEE v4.9.6 — Oracle Cloud Free VPS

Esta versão deixa o caminho principal como **Oracle Cloud VPS**.

O objetivo é parar de depender de:

- localhost.run
- Render
- link temporário
- Termux ligado 24h

## Resultado esperado

Depois de instalado na Oracle, o sistema fica em um endereço fixo:

```text
http://IP-PUBLICO-DA-ORACLE
```

Depois, com domínio:

```text
https://app.seudominio.com.br
```

Rotas principais:

```text
/sistema/status
/admin
/cliente/inicio
/app/cliente
/apk
/telegram
/inventario-profissional
/consignado-profissional
```

---

## Parte 1 — Criar servidor na Oracle

Crie uma VM Ubuntu na Oracle Cloud Free.

Configuração recomendada:

```text
Sistema: Ubuntu 22.04 ou 24.04
Tipo: Ampere/ARM ou AMD, conforme o Free Tier disponível
Disco: mínimo 50 GB
Portas liberadas na Oracle: 22, 80, 443
```

No painel da Oracle, libere na Security List/Network Security Group:

```text
TCP 22
TCP 80
TCP 443
```

Sem isso, o navegador não acessa o sistema.

---

## Parte 2 — Enviar projeto para a VPS

### Opção A: via GitHub privado

No servidor Oracle:

```bash
sudo apt update
sudo apt install -y git
git clone https://github.com/SEU-USUARIO/SEU-REPOSITORIO.git brechorisee
cd brechorisee/BRECHORISEE_SERVIDOR/app
```

Depois instale:

```bash
chmod +x oracle-install.sh
sudo ./oracle-install.sh
```

### Opção B: copiar ZIP para VPS

No seu computador, envie o ZIP ou pasta via SCP/SFTP.

Depois no servidor:

```bash
cd BRECHORISEE_SERVIDOR/app
chmod +x oracle-install.sh
sudo ./oracle-install.sh
```

---

## Parte 3 — Instalação com IP público

Sem domínio ainda:

```bash
sudo PUBLIC_BASE_URL=http://IP-PUBLICO-DA-ORACLE ./oracle-install.sh
```

Teste:

```text
http://IP-PUBLICO-DA-ORACLE/sistema/status
http://IP-PUBLICO-DA-ORACLE/admin
```

---

## Parte 4 — Instalação com domínio e HTTPS

Aponte o domínio para o IP público da Oracle.

Exemplo:

```text
app.seudominio.com.br -> IP-PUBLICO-DA-ORACLE
```

Depois rode:

```bash
sudo DOMAIN=app.seudominio.com.br PUBLIC_BASE_URL=https://app.seudominio.com.br ./oracle-install.sh
```

O script tenta configurar HTTPS com Certbot.

---

## Parte 5 — Telegram

No arquivo:

```text
/opt/brechorisee/.env
```

configure:

```env
TELEGRAM_BOT_TOKEN=seu_token
TELEGRAM_ADMIN_CHAT_ID=seu_chat_id
TELEGRAM_WEBHOOK_URL=https://app.seudominio.com.br/api/telegram/webhook
```

Sem domínio/HTTPS, o webhook do Telegram pode não funcionar como esperado. Para Telegram, use HTTPS com domínio.

Depois reinicie:

```bash
sudo systemctl restart brechorisee
```

Abra:

```text
https://app.seudominio.com.br/telegram
```

Clique em:

```text
Configurar webhook no Telegram
Enviar resumo automático
```

---

## Parte 6 — Comandos úteis

Ver se o sistema está rodando:

```bash
sudo systemctl status brechorisee
```

Ver logs ao vivo:

```bash
sudo journalctl -u brechorisee -f
```

Reiniciar:

```bash
sudo systemctl restart brechorisee
```

Parar:

```bash
sudo systemctl stop brechorisee
```

Testar local na VPS:

```bash
curl -I http://127.0.0.1:8000/sistema/status
```

Testar Nginx:

```bash
curl -I http://127.0.0.1/sistema/status
```

---

## Parte 7 — Backup

Backup manual:

```bash
sudo /opt/brechorisee/oracle-backup.sh
```

Os backups ficam em:

```text
/var/backups/brechorisee
```

Dados persistentes:

```text
/var/lib/brechorisee/brechorisee.db
/var/lib/brechorisee/uploads
/var/lib/brechorisee/static/downloads
```

---

## Parte 8 — Atualizar pelo GitHub

Depois que enviar uma nova versão para o GitHub privado:

```bash
cd /opt/brechorisee
sudo GIT_REPO=https://github.com/SEU-USUARIO/SEU-REPOSITORIO.git ./oracle-update-from-github.sh
```

---

## Problemas comuns

### Abre no servidor mas não abre no navegador

Verifique as portas no painel da Oracle:

```text
80 TCP
443 TCP
```

E no Ubuntu:

```bash
sudo ufw status
```

### Erro 502 Bad Gateway

O FastAPI não iniciou.

Veja:

```bash
sudo journalctl -u brechorisee -f
```

### Telegram não configura webhook

Use domínio com HTTPS:

```text
https://app.seudominio.com.br
```

Depois configure:

```env
TELEGRAM_WEBHOOK_URL=https://app.seudominio.com.br/api/telegram/webhook
```

### Não encontra banco/fotos

Confira:

```bash
ls -lah /var/lib/brechorisee
```

