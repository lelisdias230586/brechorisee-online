# Passo a passo - Sistema BRECHORISEE v4.8.2

## 1. Windows

Extraia o ZIP e execute:

```text
SISTEMA_BRECHORISEE.cmd
```

Aguarde compilar Cliente e Admin.

## 2. Celular servidor

Copie o conteúdo da pasta:

```text
PACOTE_CELULAR_SERVIDOR
```

para Downloads do celular servidor.

No Termux:

```bash
cd ~/storage/downloads
bash SISTEMA_BRECHORISEE_CELULAR.sh
```

## 3. Teste local

```text
http://192.168.1.18:8000
```

## 4. Teste Tailscale

```text
http://100.121.45.12:8000
```

## 5. Configurar apps

No Cliente/Admin, use:

```text
http://100.121.45.12:8000
```

O APK Cliente ficará disponível em:

```text
http://100.121.45.12:8000/apk
```
