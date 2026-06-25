(() => {
  const dataEl = document.getElementById("tutorialData");
  let tutorial = {steps: []};
  try { tutorial = JSON.parse(dataEl?.textContent || "{}"); } catch (_) {}
  const steps = tutorial.steps || [];
  const buttons = Array.from(document.querySelectorAll("[data-step-index]"));
  const focusIcon = document.getElementById("focusIcon");
  const focusKicker = document.getElementById("focusKicker");
  const focusTitle = document.getElementById("focusTitle");
  const focusText = document.getElementById("focusText");
  const cardTitle = document.getElementById("animatedCardTitle");
  const cardMeta = document.getElementById("animatedCardMeta");
  const icons = ["📲","🔔","🎥","👗","💖","🛍️","💳","✨","🌐"];
  const cards = [
    ["Abra o app ou site", "App BRECHORISEE • navegador também funciona"],
    ["Permita os avisos", "Você recebe alerta quando a live começa"],
    ["Assista no Instagram", "A live continua no Instagram da loja"],
    ["Veja a peça atual", "Foto • preço • tamanho • medidas"],
    ["Reserve com 1 toque", "Reserva principal ou fila de espera"],
    ["Acompanhe a sacola", "Todas as peças juntas em um só carrinho"],
    ["Finalize com segurança", "Pix, retirada, entrega ou WhatsApp"],
    ["Repescagem", "Peças disponíveis depois da live"],
    ["Sem app também dá", "Use o link da bio ou comentário fixado"]
  ];
  let index = 0;
  let timer = null;

  function showStep(i, manual=false) {
    if (!steps.length) return;
    index = ((i % steps.length) + steps.length) % steps.length;
    buttons.forEach((btn, pos) => btn.classList.toggle("active", pos === index));
    const step = steps[index] || {};
    if (focusIcon) focusIcon.textContent = step.icon || icons[index] || "💖";
    if (focusKicker) focusKicker.textContent = "Passo " + (index + 1);
    if (focusTitle) focusTitle.textContent = step.title || "";
    if (focusText) focusText.textContent = step.text || "";
    const card = cards[index] || cards[0];
    if (cardTitle) cardTitle.textContent = card[0];
    if (cardMeta) cardMeta.textContent = card[1];
    if (manual) restart();
  }

  function restart() {
    if (timer) clearInterval(timer);
    timer = setInterval(() => showStep(index + 1), 4200);
  }

  buttons.forEach((btn) => {
    btn.addEventListener("click", () => showStep(parseInt(btn.dataset.stepIndex || "0", 10), true));
  });
  showStep(0);
  restart();

  // Puxa a versão/roteiro atual do servidor quando disponível.
  fetch("/api/cliente/tutorial", {headers: {"Accept": "application/json"}})
    .then(r => r.ok ? r.json() : null)
    .then(payload => {
      if (!payload || !payload.ok || !payload.tutorial) return;
      tutorial = payload.tutorial;
      // A página já veio renderizada pelo servidor; esse fetch mantém a animação preparada
      // para atualizações futuras sem quebrar cache do app/PWA.
    }).catch(() => {});
})();
