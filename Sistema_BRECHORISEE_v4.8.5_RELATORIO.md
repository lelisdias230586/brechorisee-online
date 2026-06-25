# Sistema BRECHORISEE v4.8.5

Correções principais:

- Recriado o arquivo ZIP para download.
- Instalador do Termux agora encontra o servidor mesmo se a pasta ficar duplicada.
- Removido trecho Python que causava `SyntaxError` ao configurar `.env`.
- APK Cliente continua sendo o único APK publicado para clientes.
- APK Admin é compilado, mas não publicado.
- Adicionado comando `INICIAR_SISTEMA_BRECHORISEE_PUBLICO.sh` para abrir Cloudflare Tunnel.
- Mantidos Tailscale e MagicDNS:
  - `http://100.121.45.12:8000`
  - `http://m2012k11ag.tailabd299.ts.net:8000`
- Criado suporte a link público HTTPS para clientes sem Tailscale.

Uso no Windows:

```text
SISTEMA_BRECHORISEE.cmd
```

Uso no celular:

```bash
cd ~/storage/downloads
bash SISTEMA_BRECHORISEE_CELULAR.sh
```

Link público para clientes:

```bash
bash ~/INICIAR_SISTEMA_BRECHORISEE_PUBLICO.sh
```
