# Sistema BRECHORISEE v4.7.6

Correção aplicada:
- `SISTEMA_BRECHORISEE.cmd` agora executa de fato todas as etapas.
- Compila Cliente e Admin diretamente com Gradle, sem depender de vários BATs.
- Mostra o processo na tela.
- Publica `BRECHORISEE_CLIENTE.apk` no servidor.
- Cria `PACOTE_CELULAR_SERVIDOR`.
- Cria atalhos no Windows.
- Tenta envio automático por ADB quando houver celular autorizado.
- Mantém servidor oficial do celular em `http://192.168.1.18:8000`.

Observação:
- Se o celular não estiver com ADB autorizado, o envio ao celular precisa ser feito copiando o conteúdo de `PACOTE_CELULAR_SERVIDOR` para Downloads.
