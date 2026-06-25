# BRECHORISEE como servidor em celular Android

Este modo usa Termux para transformar um celular Android em servidor local da BRECHORISEE.

## Instalação

1. Instale o Termux pelo F-Droid.
2. Copie esta pasta do pacote para o celular.
3. No Termux, entre na pasta do pacote.
4. Rode:

```bash
bash BRECHORISEE_ANDROID_SERVIDOR/INSTALAR_E_INICIAR_TERMUX.sh
```

## Iniciar depois

```bash
bash BRECHORISEE_ANDROID_SERVIDOR/INICIAR_SERVIDOR_TERMUX.sh
```

## Acesso

No próprio celular:

```text
http://127.0.0.1:8000
```

Em outro aparelho na mesma rede Wi-Fi, use o IP do celular:

```text
http://IP_DO_CELULAR:8000
```

## Cuidados

- Desative economia de bateria para o Termux.
- Mantenha o celular carregando.
- Faça backup da pasta `~/brechorisee-servidor/dados`.
- Para acesso fora da rede local, use túnel gratuito como Cloudflare Tunnel, Tailscale ou Ngrok.
