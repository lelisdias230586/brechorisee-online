# Auditoria de UI/UX BRECHORISEE — 2026-09-07

## Regra de segurança

Este branch é exclusivamente de auditoria/preparação. Não autoriza deploy, alteração de produção, banco, Caddy, watchdog, router, porta 8010, fluxo InfinitePay, webhook, payment_check, refund ou reinício de backend.

O pedido financeiro E2E em andamento deve permanecer isolado.

## Estado da fonte

**Bloqueador de correção direta:** o `main` do GitHub não corresponde ao runtime atual de produção.

Evidência objetiva: `templates/online_order.html` no `main` ainda apresenta o fluxo antigo de WhatsApp/"Pagar no cartão", enquanto o runtime validado em 2026-09-07 já apresenta o fluxo InfinitePay com CTA "Pagar agora". Portanto, qualquer correção de código que toque templates/CSS compartilhados só deve ser preparada depois de sincronizar a árvore atual de produção para uma base de revisão.

## Inventário inicial de telas

| Grupo | Estado | Observação |
|---|---|---|
| Vitrine pública | PASS_WITH_UI_DEFECT | defeitos de menu/empty-state/floating controls já observados |
| Detalhe da peça | PENDING | revisar mobile e galeria |
| Sacola/checkout | PENDING | revisar mobile, formulário e CTA |
| Pedido/rastreamento | PASS_WITH_UI_DEFECT | texto sem espaçamento e CTA flutuante cobrindo conteúdo observados |
| Login/Área cliente | PENDING | revisar responsividade e estados de sessão |
| Admin dashboard | PENDING | revisar cards, ações e navegação |
| Admin produtos | PASS_WITH_UI_DEFECT | cadastro funcional; lista mostra problemas visuais em cards/galeria/overlays |
| Admin cadastro de peça | PASS_WITH_UI_DEFECT | upload de fotos voltou a funcionar; revisar composição mobile |
| Admin pedidos/vendas | PENDING | revisar tabelas e ações mobile |
| Admin clientes | PENDING | revisar grids/tabelas/formulários |
| Live/Observer/reconhecimento | PENDING | Observer instalado e diagnóstico funcional; UI ainda precisa revisão |
| Integrações/notificações | PENDING | revisar banners/fabs/permissões |
| Distribuição de apps | PASS_WITH_UI_DEFECT | segurança técnica passou; validar composição visual das páginas |

## Defeitos já confirmados visualmente

- `UI-VITRINE-001`: clipping/menu em mobile.
- `UI-VITRINE-002`: empty state duplicado.
- `UI-VITRINE-003`: controles flutuantes sobrepostos ao conteúdo.
- `UI-PEDIDO-001`: texto concatenado sem espaços: `Toque emPagar agorapara abrir a InfinitePay`.
- `UI-PEDIDO-002`: CTA/banner `Ativar avisos de pedidos` cobre conteúdo inferior.
- `UI-CATALOGO-001`: cards/imagens com proporções/recortes inconsistentes.
- `UI-CATALOGO-002`: overlays/controles interferem na leitura do card.
- `UI-MEDIA-001`: revisar responsividade das áreas de foto principal e mídias complementares.

## Achados por inspeção estática do `main`

### `templates/base.html`

- Há grande quantidade de ações no cabeçalho e navegação lateral; em mobile isso depende fortemente das regras compartilhadas de `style.css`.
- `global-search-fab` é global e precisa de zona segura para não colidir com outros elementos fixos.

### `templates/products.html`

- A `.search-row` contém 5 elementos interativos: busca, status, pesquisar, scanner e nova peça.
- O CSS desktop define `.search-row` com quatro colunas; embora exista fallback para uma coluna em telas <=700px, a faixa intermediária deve ser validada porque pode provocar wrapping/compressão inadequados.

### `templates/partials/product_card.html`

- O card assume uma única foto principal e sobrepõe `status`/`media-badge` à imagem. A produção atual apresenta uma galeria/carrossel adicional, então o componente do runtime divergiu deste `main`.

### `templates/public_store_base.html`

- Há `brecho-alert-dock`, navegação extensa, `floating-cart` e CTA de instalação na mesma base pública. Isso cria múltiplos elementos potencialmente fixos/flutuantes e explica a necessidade de uma política única de `safe-area`/`bottom-offset`.
- O rodapé ainda descreve finalização por WhatsApp, outra evidência de drift em relação ao fluxo InfinitePay atual.

### `templates/online_order.html`

- Fonte do `main` está obsoleta para o runtime atual: ainda usa WhatsApp/"Pagar no cartão" em vez do CTA InfinitePay atual.
- Não corrigir este arquivo no `main` antes da sincronização.

### `templates/online_cart.html`

- Fonte antiga ainda expõe campos manuais de Pix/link de cartão no formulário. O runtime atual tem lógica diferente. Não alterar até sincronizar.

## Estratégia de correção depois da sincronização

1. Congelar snapshot da árvore atual de produção sem tocar DB.
2. Criar branch de correção a partir desse snapshot.
3. Aplicar primeiro uma camada global de responsividade:
   - `safe-area-inset-*` consistente;
   - reserva de espaço inferior para banners/FABs;
   - evitar mais de um CTA fixo simultâneo;
   - `overflow-wrap:anywhere` para textos longos;
   - `min-width:0` em filhos de grid/flex;
   - imagens com container e `object-fit` previsíveis;
   - ações mobile em coluna/grade sem sobreposição.
4. Corrigir telas específicas.
5. Validar larguras 360, 390, 412, 480, 768 e desktop.
6. Abrir PR; nenhum deploy automático.

## Próxima ação técnica

Obter a árvore de templates/CSS/JS correspondente ao runtime de produção atual. Sem essa sincronização, qualquer patch visual no repositório corre risco de reintroduzir código funcional antigo.