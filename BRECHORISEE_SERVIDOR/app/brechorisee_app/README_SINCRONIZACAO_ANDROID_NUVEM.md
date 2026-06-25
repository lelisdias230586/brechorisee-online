# BRECHORISEE — sincronização revisada

Esta versão foi revisada com foco em **sincronizar sistema local, app Android e nuvem**.

## O que mudou

- O app Android agora não fica preso na tela de erro.
- Tela inicial com três modos:
  - **Abrir pela nuvem**
  - **Abrir servidor local**
  - **Entrar em modo offline**
- Modo offline dentro do app:
  - cadastro offline de peça;
  - cadastro offline de cliente;
  - venda offline pendente;
  - fila de pendências;
  - sincronização manual.
- Novas APIs de sincronização:
  - `GET /api/android/sync/bootstrap`
  - `POST /api/android/sync/push`
  - `GET /api/android/sync/status`
- Nova tela interna:
  - `/sincronizacao`
- Conflito de venda offline:
  - se a peça ainda estiver disponível, a venda é salva e o estoque baixa;
  - se a peça já estiver vendida/reservada, a operação fica como **conflito** para revisão;
  - o sistema não força baixa de estoque em conflito.

## Como atualizar localmente

1. Extraia este ZIP.
2. Copie seu banco antigo para a nova pasta:

```text
brechorisee_app\brechorisee.db
```

3. Copie também suas mídias, se existirem:

```text
brechorisee_app\static\uploads
brechorisee_app\static\generated
```

4. Abra o servidor:

```text
brechorisee_app\ABRIR_SERVIDOR_PARA_APP_ANDROID.bat
```

## Como atualizar o site online no Render

1. Entre no GitHub.
2. Abra o repositório `brechorisee-online`.
3. Clique em **Add file → Upload files**.
4. Envie o conteúdo da pasta `brechorisee_app`.
5. Clique em **Commit changes**.
6. O Render fará o deploy automaticamente.

Depois teste:

```text
https://brechorisee-online.onrender.com/loja
https://brechorisee-online.onrender.com/sincronizacao
```

## Como atualizar o app Android

1. Entre na pasta:

```text
brechorisee_android
```

2. Compile:

```text
COMPILAR_APK_WINDOWS.bat
```

3. No celular, desinstale o app antigo.
4. Instale o novo APK.
5. Ao abrir, você verá:
   - Abrir pela nuvem;
   - Abrir local;
   - Entrar em modo offline;
   - Pendências offline / sincronizar.

## Configuração recomendada no app

Use como nuvem:

```text
https://brechorisee-online.onrender.com
```

Use como local o IP mostrado pelo servidor no computador:

```text
http://192.168.x.x:8000
```

## Importante

Modo offline não baixa estoque imediatamente. Ele salva pendente e só confirma quando sincronizar sem conflito. Isso evita vender a mesma peça duas vezes.
