# Sistema BRECHORISEE v4.8.6 - Correção túnel externo sem Cloudflare + APK inválido

## O que foi corrigido

1. **Links públicos dinâmicos**
   - Ao acessar por `localhost.run` / `*.lhr.life`, o servidor agora usa automaticamente o domínio atual da requisição.
   - Isso evita que botões como **Baixar app** voltem para `brechorisee-online.onrender.com` ou outro link antigo salvo no `.env`.

2. **Acesso externo sem Cloudflare e sem redirecionar porta**
   - Adicionado script:
     - `INICIAR_SISTEMA_BRECHORISEE_SSH_PUBLICO.sh`
   - Depois de instalar no Termux:
     - Sessão 1: `bash ~/INICIAR_SISTEMA_BRECHORISEE.sh`
     - Sessão 2: `bash ~/INICIAR_SISTEMA_BRECHORISEE_SSH_PUBLICO.sh`

3. **APK inválido bloqueado**
   - O servidor não entrega mais qualquer arquivo como APK.
   - Agora ele valida:
     - se é ZIP/APK real;
     - se tem `AndroidManifest.xml`;
     - se tem `classes.dex`.
   - Se o APK estiver ausente ou corrompido, o botão de download não força instalação inválida.

4. **Publicação de APK mais segura**
   - `PUBLICAR_APK_CLIENTE_BRECHORISEE.sh` agora só publica APK válido.
   - Se colocar um arquivo errado em Downloads, ele será recusado.

5. **Script para salvar link público**
   - Adicionado:
     - `CONFIGURAR_LINK_PUBLICO_BRECHORISEE.sh`
   - Uso:
     ```bash
     bash ~/CONFIGURAR_LINK_PUBLICO_BRECHORISEE.sh https://SEU-LINK.lhr.life
     ```

## Passo recomendado no Termux

```bash
termux-setup-storage
cd ~/storage/downloads
unzip Sistema_BRECHORISEE_v4.8.6_CORRIGIDO.zip -d BRECHORISEE_486
cd BRECHORISEE_486
bash SISTEMA_BRECHORISEE_CELULAR.sh
```

Depois:

Sessão 1:
```bash
bash ~/INICIAR_SISTEMA_BRECHORISEE.sh
```

Sessão 2:
```bash
bash ~/INICIAR_SISTEMA_BRECHORISEE_SSH_PUBLICO.sh
```

Quando aparecer `https://....lhr.life`, acesse:

```text
https://....lhr.life/app/cliente
https://....lhr.life/admin
https://....lhr.life/apk
```

## Importante sobre o APK

Este pacote contém a correção do servidor e do projeto Android, mas não inclui um APK compilado/assinado novo. Para o botão de APK instalar corretamente, gere um APK válido pelo projeto Android e publique com:

```bash
bash ~/PUBLICAR_APK_CLIENTE_BRECHORISEE.sh
```

Enquanto não houver APK válido, a cliente pode usar normalmente pelo navegador em:

```text
https://SEU-LINK.lhr.life/app/cliente
```
