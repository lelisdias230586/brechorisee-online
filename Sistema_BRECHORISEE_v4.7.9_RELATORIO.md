# Sistema BRECHORISEE v4.7.9

Correção focada na publicação dos APKs Cliente e Admin.

## Corrigido

- O comando único do Windows agora publica os dois APKs no servidor:
  - `BRECHORISEE_CLIENTE.apk`
  - `BRECHORISEE_ADMIN.apk`
- O pacote do celular servidor leva os dois APKs.
- O instalador do Termux publica os dois APKs em:
  - `brechorisee_app/static/downloads/BRECHORISEE_CLIENTE.apk`
  - `brechorisee_app/static/downloads/BRECHORISEE_ADMIN.apk`
- O servidor agora tem rota de download para o Admin:
  - `/apk-admin`
  - `/download/app-admin.apk`
- O Cliente continua disponível em:
  - `/apk`
  - `/download/app-cliente.apk`

## Uso

Windows:

```bat
SISTEMA_BRECHORISEE.cmd
```

Celular servidor / Termux:

```bash
cd ~/storage/downloads
bash SISTEMA_BRECHORISEE_CELULAR.sh
```

Servidor oficial:

```text
http://192.168.1.18:8000
```
