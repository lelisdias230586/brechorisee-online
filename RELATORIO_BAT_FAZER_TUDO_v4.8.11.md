# BRECHORISEE v4.8.11 - BAT Fazer Tudo Windows

Adicionado o arquivo:

- `FAZER_TUDO_BRECHORISEE_WINDOWS.bat`

Ele executa o fluxo completo no Windows:

1. Confere a estrutura do projeto.
2. Remove APK Cliente antigo publicado no servidor.
3. Gera o APK Cliente release assinado.
4. Valida assinatura, `classes.dex` e `com.brechorisee.cliente.MainActivity`.
5. Publica o APK correto em `BRECHORISEE_SERVIDOR/app/brechorisee_app/static/downloads/BRECHORISEE_CLIENTE.apk`.
6. Copia o APK final para a raiz como `BRECHORISEE_CLIENTE.apk`.
7. Tenta gerar o APK Admin debug se o projeto Admin existir.
8. Cria `PACOTE_TERMUX_MINI` e `PACOTE_TERMUX_MINI.zip` para copiar ao celular.

Use no Windows, na raiz do projeto extraído:

```bat
FAZER_TUDO_BRECHORISEE_WINDOWS.bat
```
