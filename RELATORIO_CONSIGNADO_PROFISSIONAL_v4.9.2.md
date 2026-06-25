# RELATÓRIO BRECHORISEE v4.9.2 — Consignado/Montante Profissional

Esta versão segue a estabilização v4.9.1 e adiciona um módulo mais completo para consignado, montante da cliente e fechamento.

## Principais melhorias

- Nova tela `/consignado-profissional`.
- Resumo por cliente com saldo, entradas, retiradas e status.
- Registro de movimentos manuais:
  - entrada de montante;
  - devolução/crédito;
  - pagamento/acerto recebido;
  - saída manual;
  - taxa/ajuste de débito.
- Baixa de peça por código/QR reaproveitando o fluxo de venda e estoque.
- Fechamento de montante.
- Recibo em tela com opção de imprimir/salvar PDF.
- API de resposta humanizada para auxiliar o atendimento admin.
- Mensagens dos scripts de túnel revisadas para reduzir erro com `SEU-LINK` e `NOVO-LINK`.

## Novas rotas

- `/consignado-profissional`
- `/consignado-profissional/recibo/{customer_id}`
- `/api/consignado-profissional/resumo/{customer_id}`
- `/api/consignado-profissional/movimento`
- `/api/consignado-profissional/fechamento`
- `/api/chat/resposta-humanizada`

## Fluxo recomendado

1. Selecionar cliente.
2. Adicionar montante inicial.
3. Escanear/digitar código da peça.
4. Sistema debita o valor e marca a peça como vendida.
5. Registrar devoluções, pagamentos ou ajustes quando necessário.
6. Gerar fechamento.
7. Imprimir/salvar recibo em PDF.

## Próxima versão sugerida

v4.9.3 — Inventário por câmera/QR profissional, com sessões, divergências, peças sumidas, peças duplicadas e relatório final.
