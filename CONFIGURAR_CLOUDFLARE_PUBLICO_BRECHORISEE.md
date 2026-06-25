# Sistema BRECHORISEE v4.8.5 - Link público para clientes

Esta versão mantém o servidor oficial no celular Termux e adiciona um modo público para clientes usando Cloudflare Tunnel.

## Quando usar

Use quando as clientes precisam acessar o sistema, baixar o APK ou usar o app sem instalar Tailscale.

## Comando no celular

Depois de instalar o servidor no Termux, rode:

```bash
bash ~/INICIAR_SISTEMA_BRECHORISEE_PUBLICO.sh
```

O Termux vai mostrar um link parecido com:

```text
https://alguma-coisa.trycloudflare.com
```

Esse link serve para tudo:

```text
Sistema: https://alguma-coisa.trycloudflare.com
Admin:   https://alguma-coisa.trycloudflare.com/admin
Cliente: https://alguma-coisa.trycloudflare.com/app/cliente
APK:     https://alguma-coisa.trycloudflare.com/apk
```

## Importante

O link gratuito `trycloudflare.com` pode mudar quando reiniciar o túnel. Para link fixo, use um domínio próprio depois.
