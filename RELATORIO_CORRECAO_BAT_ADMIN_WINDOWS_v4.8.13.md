# RELATÓRIO - Correção BAT Fazer Tudo v4.8.13

Correção aplicada para o erro:

`Não é possível associar o argumento ao parâmetro 'ApkPath' porque ele é uma cadeia de caracteres vazia.`

## Causa

O BAT v4.8.12 tentava chamar o validador do APK Admin com a variável de caminho vazia em algumas execuções do Windows/CMD.

## Correção

- O arquivo principal `FAZER_TUDO_BRECHORISEE_WINDOWS.bat` agora chama um script PowerShell robusto.
- O fluxo completo foi movido para `FAZER_TUDO_BRECHORISEE_WINDOWS.ps1`.
- O APK Admin só é validado depois de localizar fisicamente o arquivo gerado.
- Se o APK Admin não existir, o processo para com erro claro antes de chamar o validador.
- Corrigido o problema visual `ECHO está desativado`.
- O pacote Windows só é compactado depois de a pasta existir.
- O processo não mostra mais `PRONTO` quando algum APK falha.

## Saídas geradas

- `BRECHORISEE_CLIENTE.apk`
- `BRECHORISEE_ADMIN.apk`
- `PACOTE_TERMUX_MINI`
- `PACOTE_TERMUX_MINI.zip`
- `SISTEMA_BRECHORISEE_WINDOWS`
- `SISTEMA_BRECHORISEE_WINDOWS.zip`
