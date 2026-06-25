# Correção BRECHORISEE Apps - rede local e externa

## Corrigido

- App Cliente agora aceita servidor local `http://192.168.1.18:8000` e links externos HTTPS, como LocalTunnel ou Cloudflare Tunnel.
- App Admin agora também aceita servidor local ou link externo sem precisar limpar dados.
- Tela de erro/conexão agora permite trocar o servidor direto no app.
- Botão para colar link externo foi adicionado.
- Configuração de rede Android foi ajustada para permitir HTTP local e HTTPS externo.
- O endereço salvo é normalizado: a pessoa cola apenas a base, por exemplo `https://xxxx.loca.lt`, e o app abre o caminho correto.

## Uso

No Cliente e Admin, configure somente a base:

- Local: `http://192.168.1.18:8000`
- Externo: `https://SEU-LINK.loca.lt` ou `https://SEU-DOMINIO.trycloudflare.com`

Não coloque `/admin` nem `/app/cliente` no campo do servidor.
