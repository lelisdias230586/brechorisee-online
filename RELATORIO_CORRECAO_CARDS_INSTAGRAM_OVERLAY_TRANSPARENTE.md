# Correção BRECHORISEE - Cards no Instagram e overlay Admin discreto

## Ajustes aplicados

1. App BRECHORISEE Cliente
- O botão "Abrir Instagram com card do app" agora é tratado diretamente dentro do WebView quando usa o link `brechorisee://live-companion?abrir_instagram=1`.
- Antes, em alguns aparelhos, o WebView tentava abrir o próprio app por Intent externo e o comando podia não executar o fluxo do card.
- O fluxo agora inicia o serviço de card flutuante e depois abre o Instagram nativo.
- O fallback de abertura do Instagram foi reforçado para aparelhos Xiaomi/MIUI: tenta abrir o app nativo principal e depois tenta abrir a URL/intent do Instagram.

2. App BRECHORISEE Admin
- A camada de controle/reconhecimento sobre o Instagram ficou mais discreta.
- Fundo mais transparente.
- Botões menores e sem chamar tanta atenção.
- Textos reduzidos.
- Botões "Abrir IG" e "Fechar" simplificados para "IG" e "×".

## Observação

Para os cards aparecerem por cima do Instagram, o Android precisa permitir:
`Sobrepor a outros apps` para o BRECHORISEE Cliente e para o BRECHORISEE Admin.
