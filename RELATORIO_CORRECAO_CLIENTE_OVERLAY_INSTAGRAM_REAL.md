# RELATORIO - CORRECAO CLIENTE CARDS MINIATURAS SOBRE INSTAGRAM

Correcoes aplicadas:

1. O BRECHORISEE Cliente agora inicia o `LiveCompanionOverlayService` como foreground service em Android 8+.
   - Antes: podia funcionar dentro da camera/tela interna, mas o Android podia bloquear ao abrir o Instagram.
   - Agora: o servico fica ativo e mostra notificacao discreta enquanto o card estiver ligado.

2. O card lateral fica mais discreto:
   - largura reduzida;
   - miniatura menor;
   - fundo mais transparente;
   - posicionado na lateral esquerda para nao cobrir botoes do Instagram.

3. O overlay aparece imediatamente como "carregando card" antes de abrir o Instagram.
   - Isso permite confirmar visualmente se a permissao de sobreposicao esta funcionando.

4. Fechamento:
   - botão × fecha o card;
   - live encerrada remove o card;
   - com "Acesso ao uso" autorizado, o card fecha automaticamente quando sair do Instagram.

Permissoes necessarias no celular cliente:
- Sobrepor a outros apps / Janelas flutuantes;
- Sem restrição de bateria;
- Acesso ao uso (opcional, recomendado para fechar automaticamente ao sair do Instagram).

Servidor:
- Mantido em `http://192.168.1.18:8000`.
- Nenhuma funcao anterior foi removida.
