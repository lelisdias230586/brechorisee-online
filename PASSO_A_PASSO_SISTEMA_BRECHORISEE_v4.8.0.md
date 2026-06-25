# Passo a passo — Sistema BRECHORISEE v4.8.2

## 1. No celular servidor

Instale:

- Termux pelo F-Droid
- Tailscale pela Play Store, se quiser acesso externo seguro

No Termux, rode uma vez:

```bash
termux-setup-storage
```

Toque em **Permitir**.

## 2. No Windows

Extraia o ZIP completo.

Clique duas vezes em:

```text
SISTEMA_BRECHORISEE.cmd
```

Ele vai:

1. Preparar Windows.
2. Parar servidor local antigo do PC.
3. Configurar o servidor oficial.
4. Compilar APK Cliente.
5. Compilar APK Admin.
6. Publicar somente APK Cliente.
7. Criar `PACOTE_CELULAR_SERVIDOR`.
8. Criar atalhos no PC.

## 3. Copiar para o celular

Copie o conteúdo da pasta:

```text
PACOTE_CELULAR_SERVIDOR
```

para **Downloads** do celular servidor.

## 4. Rodar no Termux

No celular servidor:

```bash
cd ~/storage/downloads
bash SISTEMA_BRECHORISEE_CELULAR.sh
```

Ele preserva banco e `.env`, publica o APK Cliente e inicia o servidor.

## 5. Acesso local

Na mesma rede Wi-Fi:

```text
Sistema: http://192.168.1.18:8000
Admin:   http://192.168.1.18:8000/admin
Cliente: http://192.168.1.18:8000/app/cliente
APK:     http://192.168.1.18:8000/apk
```

## 6. Acesso externo com Tailscale

No celular servidor, abra Tailscale e veja o IP `100.x.x.x`.

No Windows, edite:

```text
SISTEMA_BRECHORISEE_CONFIG.env
```

Preencha:

```text
TAILSCALE_URL=http://100.121.45.12:8000http://100.x.x.x:8000
```

Rode de novo:

```text
SISTEMA_BRECHORISEE.cmd
```

Depois configure o Admin/Cliente com:

```text
http://100.x.x.x:8000
```

## 7. Para iniciar o servidor depois

No Termux:

```bash
bash ~/INICIAR_SISTEMA_BRECHORISEE.sh
```

## 8. Para parar o servidor

No Termux, pressione:

```text
CTRL + C
```
