# Sistema BRECHORISEE v4.7.8

Correção aplicada:
- Removido trecho PowerShell com erro de aspas na cópia do APK.
- A rotina `SISTEMA_BRECHORISEE.cmd` agora procura o APK por lote puro:
  - primeiro `release`,
  - depois `debug`,
  - depois qualquer `.apk` em `app\build\outputs\apk`.
- Após encontrar, copia para a raiz e publica o APK Cliente no servidor.

Uso:
- Windows: `SISTEMA_BRECHORISEE.cmd`
- Celular servidor: `bash SISTEMA_BRECHORISEE_CELULAR.sh`

Servidor oficial:
- `http://192.168.1.18:8000`
