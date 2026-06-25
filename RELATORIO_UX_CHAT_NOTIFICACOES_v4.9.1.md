# RELATÓRIO BRECHORISEE v4.9.1 — UX, chat humanizado e notificações

## Objetivo
Revisar a experiência dos dois apps, melhorar a área da cliente, tornar o chat mais humano e adicionar contadores visuais de novidades no topo.

## Correções aplicadas

### 1. Área da cliente
- Botões principais transformados em botões largos, horizontais e empilhados um abaixo do outro.
- Textos mais claros em vitrine, sacola, chat, conta e tutorial.
- Melhor toque em celular, sem textos cortados.

### 2. Chat Cliente
- Adicionados botões rápidos empilhados:
  - Disponibilidade
  - Reservar
  - Pix/comprovante
  - Entrega/retirada
  - Desejo de peça
- Campo de mensagem com exemplo mais natural.
- Prevenção contra clique duplo no envio.
- Melhoria visual das bolhas do bot, cliente e atendente.

### 3. Chat Admin
- Respostas rápidas reorganizadas em botões largos e legíveis.
- Placeholder do campo de resposta orientado para atendimento humano.
- Mantida a pausa automática do bot quando a atendente responde.

### 4. Chat humanizado
- Respostas de busca de peças foram reescritas:
  - informa busca entendida;
  - mostra código, tamanho, preço, cor e status;
  - quando não encontra, salva desejo e pede refinamento com cor/tamanho/faixa/ocasião/família.

### 5. Notificações no topo
Criado painel fixo com contadores:
- mensagens;
- respostas de chat;
- live ativa;
- peças novas;
- no admin: chat, pendentes e reservas.

Nova API:
- `/api/painel-notificacoes`

### 6. Favicon
Adicionado tratamento para `/favicon.ico`, removendo erro 404 visível no log.

## Observações
Esta é uma versão de estabilização e UX. A próxima etapa recomendada é a v4.9.2, focada no consignado/montante profissional e baixa por câmera/QR.
