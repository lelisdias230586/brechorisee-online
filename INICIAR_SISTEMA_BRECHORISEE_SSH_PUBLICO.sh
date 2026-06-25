#!/data/data/com.termux/files/usr/bin/bash
set -u
PORTA="${BRECHORISEE_PORT:-8000}"
echo "============================================================"
echo " BRECHORISEE - TUNEL PUBLICO SSH / localhost.run"
echo "============================================================"
echo "Mantenha o servidor aberto em outra sessao:"
echo "bash ~/INICIAR_SISTEMA_BRECHORISEE.sh"
echo
echo "Quando aparecer uma linha terminando em .lhr.life, COPIE exatamente esse link. Nao use exemplos."
echo "Nesta versao, os botoes do site usam automaticamente o dominio atual."
echo "Para Telegram/mensagens geradas fora do navegador, salve o link com:"
echo "bash ~/CONFIGURAR_LINK_PUBLICO_BRECHORISEE.sh https://LINK-REAL-QUE-APARECEU.lhr.life"
echo
pkg install -y openssh >/dev/null 2>&1 || true
ssh -R 80:127.0.0.1:${PORTA} nokey@localhost.run
