# Sistema BRECHORISEE v4.7.10

Correção aplicada conforme pedido:

- Compila os dois apps Android:
  - BRECHORISEE Cliente
  - BRECHORISEE Admin
- Publica somente o APK Cliente no servidor para download das clientes.
- O APK Admin fica apenas como arquivo local no Windows: `BRECHORISEE_ADMIN.apk`.
- O pacote do celular servidor leva apenas:
  - servidor atualizado
  - `BRECHORISEE_CLIENTE.apk`
  - `SISTEMA_BRECHORISEE_CELULAR.sh`
- O instalador do celular remove `BRECHORISEE_ADMIN.apk` antigo de `static/downloads`, caso exista.

Links esperados após atualizar o celular servidor:

- Cliente APK: `http://192.168.1.18:8000/apk`
- Admin: acessar pelo app Admin ou pelo navegador em `http://192.168.1.18:8000/admin`, sem publicar APK Admin para clientes.
