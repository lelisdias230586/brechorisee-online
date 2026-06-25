# brechorisee — sistema local para brechó

Sistema web para cadastro, etiquetas QR Code, reconhecimento por foto, caixa, baixa de produto, fornecedoras, gráficos e IA local de apoio à compra/venda.

## O que vem pronto

- Cadastro de peças com:
  - foto;
  - código curto automático com apenas um nome e um número;
  - QR Code automático;
  - categoria, tipo de vestuário, tamanho, marca, cor, estado, medidas e características;
  - estação/ocasião, público/estilo e tags de moda;
  - custo/repasse, preço de venda e fornecedora.
- Cadastro de fornecedoras.
- Busca textual de peças por código, tipo, cor, marca, tamanho, característica, estilo, estação e fornecedora.
- Reconhecimento por foto para encontrar peça sem etiqueta.
- Caixa com:
  - inclusão por busca digitada;
  - inclusão por código;
  - leitura de QR Code pela câmera quando o navegador permite;
  - inclusão por reconhecimento de foto;
  - desconto, pagamento, troco;
  - finalização da venda com baixa automática da peça.
- Histórico de vendas e comprovante.
- Impressão de etiquetas QR Code com a identidade visual BRECHORISEE.
- Gráficos de:
  - vendas por dia;
  - compras/entradas por dia;
  - valor de compras por fornecedora;
  - estoque por tempo parado;
  - tipos de peças mais vendidos.
- Histórico de estoque com tempo estocado por peça.
- IA local para:
  - apontar peças com risco de estoque parado;
  - sugerir peças boas para vitrine;
  - analisar se uma nova peça parece boa aposta;
  - indicar possíveis peças fora do momento;
  - sugerir ações como promoção, nova foto, vitrine ou repostagem.

## Instalação rápida no Windows

1. Extraia o ZIP.
2. Entre na pasta `brechorisee_app`.
3. Dê dois cliques em:

```text
INSTALAR_WINDOWS.bat
```

O instalador cria o ambiente Python, instala as dependências e tenta criar um atalho na Área de Trabalho.

Para abrir depois, use o atalho **brechorisee** ou dê dois cliques em:

```text
INICIAR_BRECHORISEE.bat
```

Para abrir já na tela de instruções do celular, use:

```text
INICIAR_PARA_CELULAR.bat
```

## Instalação no macOS/Linux

Abra o terminal dentro da pasta `brechorisee_app` e rode:

```bash
chmod +x instalar_linux_mac.sh iniciar_linux_mac.sh criar_atalho_linux_mac.sh
./instalar_linux_mac.sh
```

Para abrir depois:

```bash
./iniciar_linux_mac.sh
```

## Instalação manual

```bash
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
```

macOS/Linux:

```bash
source .venv/bin/activate
```

Depois:

```bash
pip install -r requirements.txt
python app.py
```

Abra no navegador:

```text
http://127.0.0.1:8000
```

Para usar no celular, abra a página:

```text
http://127.0.0.1:8000/celular
```


## Uso pelo celular — principal desta versão

Esta versão foi ajustada para o celular ser o ponto principal de operação do brechorisee.

1. Instale e abra o sistema no computador.
2. O terminal mostrará dois endereços:
   - computador: `http://127.0.0.1:8000`
   - celular: algo como `http://192.168.0.10:8000`
3. Conecte o celular na mesma rede Wi‑Fi do computador.
4. Abra o endereço do celular no navegador.
5. Entre em `Usar no celular` ou abra `/celular` para ver instruções e copiar o link.
6. No Android, use o botão **Instalar app** quando aparecer ou o menu do Chrome.
7. No iPhone, use **Compartilhar → Adicionar à Tela de Início**.

### O que funciona pelo celular

- Cadastro de peça com câmera traseira usando o botão de foto.
- Foto para reconhecimento quando a etiqueta sumir.
- Caixa completo pelo celular.
- Inclusão no caixa por busca digitada.
- Inclusão no caixa por código digitado.
- Leitura ao vivo de QR/código quando o navegador permitir.
- Gráficos, histórico, IA e etiquetas em telas responsivas.
- Atalhos inferiores para painel, peças, caixa, foto e modo celular.

### Observação sobre câmera e QR ao vivo

Foto de peça e reconhecimento usam o seletor de câmera do próprio celular e são o fluxo principal.
Scanner ao vivo de QR/código usa recursos do navegador, que podem depender de permissão, modelo do celular e segurança do endereço.
Se o scanner ao vivo não abrir, o sistema continua funcionando por busca digitada, código digitado e reconhecimento de foto.


## Como funciona a IA

A IA desta versão é **local** e não envia dados nem fotos para fora do computador. Ela usa:

- histórico de vendas;
- tempo de estoque de cada peça;
- margem estimada;
- giro de peças parecidas;
- palavras de tendência e alerta configuradas no arquivo `ai_config.json`.

O arquivo `ai_config.json` pode ser editado pela loja. Exemplo: se o brechorisee perceber que "linho", "alfaiataria" ou "vintage" estão vendendo melhor, mantenha essas palavras em `trend_keywords`. Se quiser sinalizar problemas, use `attention_keywords`, como "mancha", "avaria" ou "bolinha".

Esta versão **não consulta tendências da internet**. Para uma versão futura, dá para conectar uma API externa de moda/redes sociais sem mudar o fluxo principal do sistema.

## Arquivos importantes

- `brechorisee.db`: banco de dados local.
- `static/uploads`: fotos das peças.
- `static/qrcodes`: QR Codes gerados.
- `ai_config.json`: critérios editáveis da IA.
- `install.py`: instalador multiplataforma.
- `INICIAR_BRECHORISEE.bat` / `iniciar_linux_mac.sh`: abridores do sistema.

## Observações

- A leitura de QR pela câmera depende do suporte do navegador ao `BarcodeDetector`. Quando não houver suporte, use a busca digitada, digite o código manualmente ou pesquise por foto.
- O reconhecimento por foto é leve e local, usando assinatura visual da imagem. Para produção, pode evoluir para embeddings/IA visual mais avançada.
- Nos gráficos, "compras" significa entrada de peças multiplicada pelo custo/repasse informado no cadastro.

## Atualização: busca por digitação

Esta versão inclui busca digitada também na tela de reconhecimento/foto e no caixa. No caixa, pesquise por palavras como `vestido preto P`, `jeans`, `bolsa couro`, marca, tamanho, cor, estilo ou parte do código; depois toque em **Adicionar** para colocar a peça no carrinho.


## Logo e códigos curtos

Esta versão aplica o logo BRECHORISEE nas telas, no app instalado e nas etiquetas.

No cadastro de peça, o código é gerado automaticamente com este padrão:

```text
NOME-001
```

Exemplos:

```text
VESTIDO-001
AMORA-002
FARM-003
FLORAL-004
```

O sistema usa os campos preenchidos no cadastro para escolher apenas um nome:
tipo de vestuário, estampa, marca da roupa, cor, características ou uma fruta estilizada quando for melhor. O código continua funcionando no QR Code, no caixa, na busca digitada e na baixa de produto.

Você pode editar o código manualmente no cadastro; mesmo assim, o sistema ajusta para o padrão de um nome e um número.


## App Android BRECHORISEE

Esta versão também vem com uma pasta chamada `brechorisee_android`, que contém um app Android nativo em WebView para usar o sistema no celular sem abrir o navegador manualmente.

### Como ele fica interligado ao banco local

O banco principal continua sendo o arquivo local:

```text
brechorisee_app\brechorisee.db
```

O computador roda o servidor local e o app Android acessa esse servidor pelo Wi‑Fi. Assim, computador e celular usam os mesmos dados: cadastro, fotos, estoque, caixa, vendas, relatórios e IA local.

Para usar:

1. No computador, abra:

```text
ABRIR_SERVIDOR_PARA_APP_ANDROID.bat
```

2. Anote o endereço mostrado, parecido com:

```text
http://192.168.0.10:8000
```

3. Compile o app na pasta `brechorisee_android` com:

```text
COMPILAR_APK_WINDOWS.bat
```

4. Instale o APK `BRECHORISEE_android.apk` no celular.
5. Ao abrir o app, digite o endereço do servidor local.

Se o app não conectar, verifique se o celular está no mesmo Wi‑Fi, se o computador está ligado e se a porta 8000 foi liberada no firewall. Para liberar no Windows, execute como administrador:

```text
LIBERAR_FIREWALL_WINDOWS.bat
```


## Atualização: fotos e vídeos complementares

O cadastro de peças agora aceita uma foto principal e vários arquivos complementares, incluindo fotos de detalhes e vídeos curtos. As fotos complementares entram na busca por reconhecimento visual; os vídeos ficam vinculados ao cadastro para conferência, divulgação, pesquisa e histórico da peça.

No Android, recompile o APK com `brechorisee_android\COMPILAR_APK_WINDOWS.bat` para liberar seleção de várias fotos/vídeos no app.


## Atualização Instagram avançado

O módulo Instagram agora permite escolher modelo visual, selo automático/manual, gerar arte final em PNG, gerar slides de carrossel, criar reel em MP4 e compartilhar/baixar os arquivos pelo celular.

Modelos disponíveis: Minimalista claro, Chic clean, Promoção/Achadinho e Luxo escuro.

Os arquivos gerados ficam em:

`brechorisee_app/static/generated/marketing`


## Atualização Gestão 360 — melhorias 1 ao 20

Esta versão acrescenta a aba **Gestão 360**, com base funcional para:

1. clientes completos;
2. reservas com prazo;
3. lista de desejos;
4. mensagens de WhatsApp;
5. repasse/fornecedoras;
6. despesas e resultado financeiro;
7. promoções automáticas;
8. etiquetas profissionais;
9. backup ZIP do banco, fotos, vídeos e conteúdos;
10. usuários/perfis;
11. vitrine inteligente;
12. campanhas de Instagram/WhatsApp;
13. montador de looks;
14. provador por medidas;
15. ranking de interesse;
16. lotes de entrada;
17. conferência por câmera;
18. trocas/devoluções;
19. recibos;
20. estrutura para offline/sincronização futura.

Abra a aba **Gestão 360** no menu lateral.


## Atualização mobile

O menu inferior foi removido para não atrapalhar a visão do painel no celular. Todos os atalhos continuam disponíveis no botão de três pontinhos no topo.
