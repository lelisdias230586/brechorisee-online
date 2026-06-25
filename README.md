# Sistema BRECHORISEE v4.8.8

Correção: bloqueia APK antigo/incompatível que instala e fecha ao abrir. Cliente não entra direto na live após login/cadastro.

# Sistema BRECHORISEE v4.8.5


Versão corrigida para abrir corretamente no Windows.

## Use no Windows
1. Extraia o ZIP.
2. Clique em `SISTEMA_BRECHORISEE.cmd`.
3. Se não abrir, clique em `ABRIR_SISTEMA_BRECHORISEE.cmd`.
4. Se o Windows bloquear, clique com botão direito no arquivo `.cmd`, Propriedades, marque Desbloquear e Aplicar.

## Servidores
- Local: `http://192.168.1.18:8000`
- Tailscale: `http://100.121.45.12:8000`
- MagicDNS: `http://m2012k11ag.tailabd299.ts.net:8000`

## Publicação
Compila Cliente e Admin, mas publica somente o APK Cliente.

# Sistema BRECHORISEE v4.8.2

Correção principal: publicação do APK Cliente no servidor do celular.

Dados configurados:

- Local: http://192.168.1.18:8000
- Tailscale: http://100.121.45.12:8000
- MagicDNS: http://m2012k11ag.tailabd299.ts.net:8000

## Windows

Execute:

```cmd
SISTEMA_BRECHORISEE.cmd
```

Ele compila Cliente e Admin, publica somente o APK Cliente e cria `PACOTE_CELULAR_SERVIDOR`.

## Celular servidor / Termux

Copie o conteúdo de `PACOTE_CELULAR_SERVIDOR` para Downloads do celular e execute:

```bash
cd ~/storage/downloads
bash SISTEMA_BRECHORISEE_CELULAR.sh
```

## Correção rápida se a página /apk mostrar "APK ainda não publicado"

Copie `BRECHORISEE_CLIENTE.apk` para Downloads do celular e rode:

```bash
bash ~/PUBLICAR_APK_CLIENTE_BRECHORISEE.sh
```

ou, se ainda não instalou a versão nova:

```bash
cd ~/storage/downloads
bash PUBLICAR_APK_CLIENTE_BRECHORISEE.sh
```

Depois teste:

- http://100.121.45.12:8000/apk
- http://192.168.1.18:8000/apk


## Atualização v4.8.4

Correção: o Windows agora compila mesmo quando não existe `gradlew.bat`, usando o Gradle baixado em `tools/gradle-8.10.2`.


## v4.8.5

Inclui link público para clientes com Cloudflare Tunnel. No celular, após instalar, rode:

```bash
bash ~/INICIAR_SISTEMA_BRECHORISEE_PUBLICO.sh
```

O APK Cliente fica em `/apk`. O APK Admin não é publicado.


## v4.9.3 - Inventário profissional e Telegram

- Tela `/inventario-profissional`
- Painel `/telegram`
- Controle por bot Telegram com mensagens, botões, avisos e métricas
- `.env` preparado com as configurações enviadas

