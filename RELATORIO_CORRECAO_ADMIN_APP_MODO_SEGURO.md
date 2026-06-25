# Correção BRECHORISEE Admin - Modo seguro

Foi aplicado modo seguro no app Android Admin para evitar fechamento imediato quando o Android WebView/Chrome estiver desatualizado, quando houver erro de permissão ou quando o servidor ainda não estiver disponível.

## Alterações
- `MainActivity.onCreate()` agora protege a inicialização com `try/catch`.
- Nova tela nativa de modo seguro com botões:
  - Tentar abrir novamente
  - Abrir Play Store / Android System WebView
  - Abrir Play Store / Chrome
  - Abrir Admin no navegador
- Mensagem offline atualizada para orientar uso com celular servidor BRECHORISEE.
- Nenhuma função do backend/admin/cliente foi removida.
