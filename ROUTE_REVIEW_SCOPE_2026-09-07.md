# Escopo de rotas para revisão visual

## Público/cliente
- `/loja`
- `/loja/produto/{code}`
- `/loja/carrinho`
- `/loja/pedido/{token}`
- `/cliente`
- `/cliente/login`
- `/cliente/perfil`
- `/cliente/entregas`
- `/cliente/chat`
- `/cliente/novidades`
- `/cliente/live`
- `/cliente/live-opcoes`
- `/cliente/tutorial`
- `/live/peca-atual`
- `/app`
- `/app/cliente`

## Admin
- `/admin-acesso`
- `/`
- `/products`
- `/products/new`
- `/products/{id}`
- `/sales`
- `/loja-admin`
- `/clientes-inteligentes`
- `/deliveries`
- `/notificacoes`
- `/live`
- `/recognize`
- `/instagram-studio`
- `/telegram`
- `/admin/apps`
- `/admin/apps/admin`
- `/admin/apps/live`

## Critério por tela
- `PASS`
- `PASS_WITH_UI_DEFECT`
- `FAIL_FUNCTIONAL`
- `PENDING`

## Validações mínimas por viewport
- 360 x 800
- 390 x 844
- 412 x 915
- 480 x 960
- 768 x 1024
- desktop >= 1280

## Checklist visual
- sem overflow horizontal inesperado;
- sem elementos fixos cobrindo CTA/card/form;
- sem texto concatenado ou truncado de forma indevida;
- botões com área de toque suficiente;
- imagens sem distorção;
- carrossel/galeria sem invadir conteúdo textual;
- filtros e selects sem clipping;
- safe-area superior/inferior respeitada;
- estados vazio/erro/carregando únicos e consistentes;
- campos de formulário legíveis em teclado mobile;
- tabelas com scroll horizontal controlado quando inevitável.