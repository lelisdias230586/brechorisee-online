# Correção BRECHORISEE Cliente - Cards miniaturas no Instagram

## Ajustes aplicados

- O card flutuante do app Cliente agora aparece como miniatura lateral por cima do Instagram.
- O card não some mais após poucos segundos de peça ativa.
- O card permanece enquanto a live estiver ao vivo.
- Ao encerrar a live, o card some automaticamente.
- Ao tocar no botão `×`, o card some.
- Ao fechar/remover o app Cliente, o serviço remove o overlay.
- Em modo miniatura, apenas a miniatura lateral e o botão fechar ficam visíveis.
- A permissão necessária continua sendo: Sobrepor a outros apps.

## Arquivo alterado

- `BRECHORISEE_CLIENTE/android/app/src/main/java/com/brechorisee/cliente/LiveCompanionOverlayService.java`

## Observação

Depois de compilar e instalar o novo APK Cliente, no celular da cliente é necessário permitir:

`Configurações > Apps > BRECHORISEE Cliente > Sobrepor a outros apps > Permitir`
