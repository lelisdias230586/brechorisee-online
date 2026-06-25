# Sistema BRECHORISEE v4.7.3

Correção aplicada:
- O instalador do celular preserva banco de dados existente.
- O instalador do celular preserva o `.env` existente, incluindo Telegram e senhas.
- O instalador do celular publica automaticamente o APK Cliente quando encontrar `BRECHORISEE_CLIENTE.apk` ou `BRECHORISEE_CLIENTE_RELEASE.apk` em Downloads.
- O Windows continua com um único arquivo principal: `SISTEMA_BRECHORISEE.cmd`.
- O celular servidor continua com um único comando: `bash SISTEMA_BRECHORISEE_CELULAR.sh`.

Servidor oficial:
`http://192.168.1.18:8000`

Para corrigir a tela "APK ainda não publicado":
1. Copie `BRECHORISEE_CLIENTE.apk` para Downloads do celular servidor.
2. Copie/descompacte este pacote em Downloads.
3. Rode:
   ```bash
   cd ~/storage/downloads
   bash SISTEMA_BRECHORISEE_CELULAR.sh
   ```
4. Abra:
   `http://192.168.1.18:8000/apk`
