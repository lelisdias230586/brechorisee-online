# Achados iniciais de layout mobile — 2026-09-07

## Confirmados por evidência visual

- UI-VITRINE-001 — menu/clipping em mobile.
- UI-VITRINE-002 — estado vazio duplicado.
- UI-VITRINE-003 — botões/controles flutuantes sobrepondo conteúdo.
- UI-PEDIDO-001 — texto concatenado na instrução de pagamento.
- UI-PEDIDO-002 — banner `Ativar avisos de pedidos` cobre conteúdo inferior.
- UI-CATALOGO-001 — cards/imagens com proporção/recorte inconsistente.
- UI-CATALOGO-002 — overlays de galeria interferem na leitura do card.
- UI-MEDIA-001 — revisar layout de foto principal e mídias complementares.

## Achados estáticos do `main`

1. `base.html` contém `global-search-fab` global, além de navegação e ações numerosas; precisa coexistir com qualquer outro componente fixo sem colisão.
2. `public_store_base.html` combina `brecho-alert-dock`, navegação extensa, `floating-cart` e CTA adicional na base pública.
3. `products.html` usa uma `.search-row` com 5 controles; o CSS desktop define 4 colunas. Há fallback para 1 coluna em <=700px, mas a faixa intermediária requer correção/validação.
4. `product_card.html` do `main` não contém a galeria/carrossel que aparece no runtime atual, confirmando drift.
5. `online_order.html` e `online_cart.html` do `main` ainda representam o fluxo antigo e não devem receber patch de produção.

## Correção global proposta depois do sync

- criar uma única variável de offset inferior para elementos fixos;
- nunca renderizar simultaneamente CTA fixo + FAB + banner sobre o mesmo eixo sem stacking explícito;
- adicionar `padding-bottom` equivalente ao maior overlay ativo;
- usar `min-width:0` em itens de grid/flex com texto;
- definir containers de mídia com altura/aspect-ratio consistente e `object-fit:cover`;
- garantir `overflow-wrap:anywhere` para identificadores, SHA, URLs e labels longos;
- padronizar ações em mobile para grid de 1 coluna ou 2 colunas quando houver espaço real;
- validar 360/390/412/480/768 px.