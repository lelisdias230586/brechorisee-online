# Tutorial animado da cliente BRECHORISEE

Implementado nesta versão:

- Página pública `/cliente/tutorial`
- Alias `/app/tutorial` e `/tutorial-cliente`
- API pública `/api/cliente/tutorial`
- Animação em HTML/CSS/JS, sem depender de vídeo externo
- Passo a passo para:
  - baixar/abrir app;
  - continuar sem app pelo navegador;
  - permitir notificações;
  - assistir a live no Instagram;
  - usar o card flutuante da peça atual;
  - reservar/entrar na fila;
  - acompanhar sacola/carrinho;
  - finalizar Pix/retirada/entrega;
  - acessar repescagem/vitrine.
- Link “Como usar” nas áreas públicas da cliente.
- O app Android cliente abre o tutorial na primeira inicialização de uma instalação nova.
- Deep links adicionados:
  - `brechorisee://tutorial`
  - `brechorisee://como-usar`
  - `brechorisee://ajuda-cliente`

## Atualização automática por versão

O tutorial usa `BRECHORISEE_VERSION` do `.env`/Render.  
Quando uma nova versão for publicada, a página mostra automaticamente a versão atual e a API entrega o roteiro atualizado.

Rotas importantes:

- `https://SEU-DOMINIO/cliente/tutorial`
- `https://SEU-DOMINIO/api/cliente/tutorial`
- `https://SEU-DOMINIO/app/cliente`

## Onde aparece

- Menu da vitrine cliente
- CTA fixo da vitrine
- Página de baixar app
- Página da peça
- Opções da live
- Companion da live
- Área da cliente
- Mensagens automáticas via `brechorisee_customer_app_cta`

## Observação

A animação é gerada dentro do próprio projeto usando HTML/CSS/JS.  
Não precisa hospedar vídeo, GIF ou imagem pesada.
