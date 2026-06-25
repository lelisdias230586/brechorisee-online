# App Android BRECHORISEE

Este projeto cria um app Android nativo simples para usar o sistema BRECHORISEE no celular.

Ele foi feito para compilar por `.bat`, sem abrir Android Studio.

## Como funciona o banco de dados local

O banco principal continua no computador, dentro da pasta do sistema:

```text
brechorisee_app\brechorisee.db
```

O app Android acessa o sistema local pelo Wi‑Fi. Assim, os dois ficam interligados:

- cadastro pelo celular aparece no computador;
- foto tirada pelo celular salva no sistema local;
- venda feita no app baixa o estoque no mesmo banco;
- gráficos, histórico e IA leem os mesmos dados.

Não é nuvem. O computador funciona como servidor local.

## Passo 1 — abrir o servidor local

Na pasta `brechorisee_app`, rode:

```text
ABRIR_SERVIDOR_PARA_APP_ANDROID.bat
```

O sistema vai mostrar um endereço parecido com:

```text
http://192.168.0.10:8000
```

Guarde esse endereço para colocar no app.

## Passo 2 — compilar o APK

Na pasta `brechorisee_android`, dê dois cliques em:

```text
COMPILAR_APK_WINDOWS.bat
```

Na primeira execução, o `.bat` pode baixar:

- Android SDK command-line tools;
- plataforma Android 35;
- build-tools;
- Gradle;
- dependências do Android.

Isso pode demorar. Não precisa abrir Android Studio.

Requisito: Java/JDK 17 ou superior instalado.

No final será gerado:

```text
BRECHORISEE_android.apk
```

## Passo 3 — instalar no Android

Opção A: copie `BRECHORISEE_android.apk` para o celular e toque nele para instalar.

Opção B: com depuração USB ativada, use:

```text
INSTALAR_NO_CELULAR_USB.bat
```

## Passo 4 — primeira abertura

Abra o app BRECHORISEE no celular e informe o endereço mostrado pelo computador:

```text
http://192.168.0.10:8000
```

O app salva esse endereço. Para trocar depois, toque no botão de engrenagem dentro do app.

## Se não conectar

Verifique:

1. computador e celular no mesmo Wi‑Fi;
2. servidor local aberto no computador;
3. endereço IP digitado corretamente;
4. firewall permitindo a porta 8000.

No Windows, execute como administrador:

```text
brechorisee_app\LIBERAR_FIREWALL_WINDOWS.bat
```

## Observações sobre câmera

O app permite usar câmera/galeria para cadastro e reconhecimento de peças. O fluxo principal de foto funciona pelo seletor nativo do Android. Leitura ao vivo de QR/código depende do suporte do WebView e das permissões do aparelho; busca digitada, código e reconhecimento por foto continuam funcionando.


## Correção incluída

Esta versão corrige o erro `Expand-Archive -Path '' -DestinationPath ''` no instalador automático do Android SDK.
Se uma tentativa antiga deixou o SDK incompleto, apague `%LOCALAPPDATA%\Android\Sdk\cmdline-tools\latest` e rode `COMPILAR_APK_WINDOWS.bat` novamente.


## Preenchimento rápido e voz

Esta versão inclui:

- listas de sugestões em campos de cadastro, busca, caixa e fornecedoras;
- botão 🎙️ ao lado dos campos para ditar texto no Android;
- permissão de microfone solicitada somente quando você usar a voz;
- sugestões criadas com listas padrão + histórico do próprio banco local.

No cadastro de peça, toque no campo para abrir as sugestões. No app Android, toque em 🎙️ e fale, por exemplo:

```text
Bolsa preta de couro com alça regulável
```

O sistema preenche o campo ativo e mantém o código no padrão:

```text
NOME-001
```

Exemplo:

```text
BOLSA-001
```


## Integração com app da maquininha

Esta versão inclui o fluxo de maquininha no caixa:

1. coloque as peças no carrinho;
2. escolha Pix, Cartão de débito, Cartão de crédito ou Misto;
3. mantenha marcada a opção **Abrir app da maquininha antes de salvar**;
4. toque em **Finalizar venda**;
5. o Android abre o app da maquininha configurado;
6. depois que o pagamento for aprovado na maquininha, volte para o BRECHORISEE;
7. toque em **Pagamento confirmado • salvar venda**.

Enquanto você não confirmar, a venda não é salva e o estoque não é baixado.

### Configurar o app da maquininha

No caixa, abra **Configurar maquininha**.

O jeito mais fácil é tocar em **Escolher app instalado** e selecionar o app da maquininha na lista.

Também é possível preencher manualmente:

```text
Pacote do app da maquininha
```

ou

```text
Link/deeplink opcional
```

O campo de deeplink aceita estes marcadores:

```text
{amount}
{valor}
{amount_cents}
{valor_centavos}
{method}
{forma}
{reference}
{referencia}
```

Exemplo genérico:

```text
app://payment?amount={amount_cents}&ref={reference}
```

Cada empresa de maquininha usa um pacote/link/SDK próprio. Sem integração oficial da maquininha, o Android consegue abrir o app, mas não consegue saber sozinho se o pagamento foi aprovado. Por isso o BRECHORISEE só salva depois do toque em **Pagamento confirmado**.

Se a sua maquininha tiver retorno por deeplink, use como retorno:

```text
brechorisee://pagamento?status=aprovado
```

Com esse retorno, o BRECHORISEE consegue receber o status e salvar automaticamente quando houver uma venda aguardando confirmação.


## Fotos e vídeos

Esta versão do app Android permite escolher várias fotos e vídeos da galeria para complementar o cadastro da peça. A foto principal continua aparecendo no estoque; as fotos complementares também entram no reconhecimento visual. Vídeos ficam salvos no servidor local para conferência e histórico.
