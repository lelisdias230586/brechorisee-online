# BRECHORISEE - Download do APK Cliente

O APK não precisa ficar no GitHub nem no Render.

No modelo novo, ele fica publicado pelo próprio servidor BRECHORISEE:

- Notebook Windows servidor
- Celular Android servidor com Termux
- Qualquer computador na mesma rede

## Link para as clientes

Com o servidor ligado, as clientes acessam:

```text
http://IP_DO_SERVIDOR:8000/app/cliente
```

Download direto:

```text
http://IP_DO_SERVIDOR:8000/download/app-cliente.apk
```

Atalho:

```text
http://IP_DO_SERVIDOR:8000/apk
```

## Windows

1. Gere o APK cliente.
2. Abra `BRECHORISEE_WINDOWS\ABRIR_BRECHORISEE_WINDOWS.bat`.
3. Clique em `Publicar APK Cliente`.
4. Clique em `Página de instalação`.
5. Envie o link para as clientes.

Também pode rodar:

```bat
BRECHORISEE_WINDOWS\PUBLICAR_APK_CLIENTE_NO_SERVIDOR_WINDOWS.bat
```

## Android servidor

Copie o APK para:

```text
BRECHORISEE_SERVIDOR/app/brechorisee_app/static/downloads/BRECHORISEE_CLIENTE.apk
```

Depois abra:

```text
http://IP_DO_CELULAR:8000/app/cliente
```

## Acesso fora da loja/casa

Para clientes baixarem de fora da sua rede Wi-Fi, será necessário um túnel gratuito, como Cloudflare Tunnel, Tailscale ou Ngrok.
