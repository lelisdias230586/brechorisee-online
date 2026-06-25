# Segurança dos dados — guia para preencher no Play Console

Use este guia para preencher a seção **Segurança dos dados** do Google Play Console.

## Coleta de dados

O app pode coletar dados informados pela cliente para funcionamento da loja:

### Informações pessoais
- Nome
- Telefone/WhatsApp
- Endereço de entrega, quando informado
- E-mail, se a loja solicitar em algum fluxo futuro

Finalidade:
- gestão de reserva
- carrinho/pedido
- entrega ou retirada
- suporte ao cliente

### Informações financeiras
O app pode mostrar Pix ou receber comprovante, mas não deve armazenar dados de cartão no app.

Finalidade:
- confirmação de pagamento
- suporte de pedido

### Fotos e arquivos
O app pode permitir que a cliente envie comprovante ou imagem por upload, quando ela escolhe essa ação.

Finalidade:
- confirmação de pagamento
- atendimento/suporte

### Atividade no app
O sistema pode registrar reservas, fila de espera, carrinho, pedidos, notificações e interações com a live.

Finalidade:
- funcionamento da loja
- prevenção de erro/fraude
- atendimento
- melhoria do serviço

### Identificadores do dispositivo
O app pode usar identificadores técnicos locais para sessão, notificações e funcionamento do WebView.

Finalidade:
- manter sessão
- entregar avisos
- segurança operacional

## Compartilhamento de dados

Marque que os dados podem ser processados por prestadores necessários ao funcionamento, como hospedagem, atendimento, mensagens, entrega e pagamento, quando aplicável.

Não marcar venda de dados.

## Segurança

Informar que:
- os dados são transmitidos por conexão HTTPS quando em produção;
- o app não vende dados;
- a cliente pode solicitar exclusão de dados em `/excluir-dados`.

## Exclusão de dados

URL:

```txt
https://brechorisee-online.onrender.com/excluir-dados
```

## Declaração importante sobre Instagram

O app não coleta senha do Instagram, não lê mensagens privadas, não captura a tela da cliente, não grava áudio e não interage diretamente com a conta da cliente no Instagram.

## Permissão de sobreposição

Quando a permissão de sobreposição for ativada pela cliente, ela serve apenas para mostrar o card BRECHORISEE da peça atual sobre outros apps, como o Instagram, sem leitura de tela.
