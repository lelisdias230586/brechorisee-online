# RELATÓRIO - CONFIGURAÇÃO NO PRIMEIRO ACESSO DO CLIENTE

Correção aplicada no app **BRECHORISEE Cliente**.

## O que mudou

Ao abrir o app Cliente pela primeira vez, agora aparece uma tela de configuração antes de usar o app:

1. Campo para informar o servidor BRECHORISEE.
2. Botão para permitir cards sobre o Instagram.
3. Botão para permitir acesso ao uso, para fechar cards ao sair do Instagram.
4. Botão para abrir configurações de bateria sem restrição.
5. Botão para testar conexão com o servidor.
6. Botão para salvar e abrir o Cliente.
7. Botão para salvar e abrir Instagram com cards.

## Servidor padrão configurado

```text
http://192.168.1.18:8000
```

## Arquivo alterado

```text
BRECHORISEE_CLIENTE/android/app/src/main/java/com/brechorisee/cliente/MainActivity.java
```

## Objetivo

Evitar que a cliente instale o app e tente usar os cards sem selecionar as permissões necessárias.
