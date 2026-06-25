BRECHORISEE - Revisão de cadastro com fotos e vídeos

Correções aplicadas:
1. App Admin Android agora trata upload de arquivo no WebView:
   - foto principal
   - galeria
   - câmera
   - múltiplas fotos
   - vídeos
   - retorno correto do arquivo ao formulário
2. App Cliente Android também recebeu o mesmo tratamento para evitar tela branca/falha em campos de arquivo.
3. Manifest mantém permissões de câmera, imagens e vídeos.
4. Formulário de cadastro permanece com enctype multipart/form-data.
5. Visual do campo de arquivo foi corrigido para não aparecer o botão nativo "Escolher arquivo" por cima da tela.
6. Prévia de foto e mídias continua funcionando.
7. Botão de salvar mostra "Salvando peça e arquivos..." para evitar clique duplicado.

Como atualizar:
1. Suba a pasta brechorisee_app no GitHub.
2. No Render, use Clear build cache & deploy.
3. Compile novamente:
   - brechorisee_admin_android/COMPILAR_APK_WINDOWS.bat
   - brechorisee_cliente_android/COMPILAR_APK_WINDOWS.bat
4. Desinstale os apps antigos do celular.
5. Instale os APKs novos.

Teste obrigatório:
1. No app Admin, abrir Cadastrar peça.
2. Tirar foto principal pela câmera.
3. Escolher foto principal pela galeria.
4. Adicionar 2 fotos complementares.
5. Adicionar 1 vídeo curto.
6. Salvar peça.
7. Abrir a peça e confirmar se a galeria aparece.
8. Abrir /loja e confirmar se a foto principal aparece na vitrine.
