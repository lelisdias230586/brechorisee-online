# Sistema BRECHORISEE v4.7.6

## Correção aplicada

O pacote foi reorganizado para atender ao pedido:

> instalação no Windows, compilação dos dois APKs, publicação do APK, configuração e atalhos com apenas um comando.

## Comando único no Windows

```bat
SISTEMA_BRECHORISEE.cmd
```

## Comando único no celular servidor

```bash
cd ~/storage/downloads
bash SISTEMA_BRECHORISEE_CELULAR.sh
```

## Servidor oficial

```text
http://192.168.1.18:8000
```

## Preservação

A estrutura principal do Sistema BRECHORISEE foi mantida:

- BRECHORISEE_SERVIDOR
- BRECHORISEE_CLIENTE
- BRECHORISEE_ADMIN
- BRECHORISEE_ANDROID_SERVIDOR
- BRECHORISEE_WINDOWS

O instalador do celular preserva banco e `.env` existentes.
