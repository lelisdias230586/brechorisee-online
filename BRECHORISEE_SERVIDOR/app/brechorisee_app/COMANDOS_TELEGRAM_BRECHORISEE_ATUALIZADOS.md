# Comandos Telegram BRECHORISEE atualizados

Agora o bot interno responde também com uma lista de comandos quando a equipe envia:

- `/comandos`
- `/comandos live`
- `/comandos pedido`
- `/pedido`
- `/pedido ajuda`
- `/pedido ID ajuda`
- `/brechorisee`

## O que foi corrigido

Antes, quando a equipe enviava apenas `/pedido`, o sistema podia responder como comando não reconhecido.  
Agora `/pedido` retorna o menu de pedidos com exemplos prontos:

```txt
/pedido ID
/pedido ID pago
/pedido ID cancelar
/pedido ID entrega
/pedido ID entregue
/pedidos
/cliente NOME_OU_TELEFONE
```

## Menus disponíveis

### Menu geral

```txt
/comandos
```

### Menu da live

```txt
/comandos live
```

### Menu de pedidos

```txt
/comandos pedido
```

## Exemplos úteis

```txt
/pedido 1 pago
/pedido 1 cancelar
/addfila CROPPED-001
/reservar Maria | 48999999999
/pago Maria
```

Depois de subir esta versão no Render, faça redeploy e teste no Telegram enviando `/comandos` e `/pedido`.
