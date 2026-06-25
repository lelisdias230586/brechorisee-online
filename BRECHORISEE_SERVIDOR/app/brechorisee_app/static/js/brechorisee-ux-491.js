(() => {
  const dock = document.querySelector('[data-brecho-alert-dock]');
  if (!dock) return;

  const counters = Array.from(dock.querySelectorAll('[data-alert-count]'));
  function setCount(kind, value) {
    const n = Math.max(0, Number(value || 0));
    dock.querySelectorAll(`[data-alert-kind="${kind}"]`).forEach(el => {
      el.classList.toggle('has-alert', n > 0);
      const b = el.querySelector('[data-alert-count]');
      if (b) b.textContent = n > 99 ? '99+' : String(n);
      el.setAttribute('aria-label', `${el.textContent.replace(/\s+/g,' ').trim()} ${n > 0 ? 'com novidades' : 'sem novidades'}`);
    });
  }

  async function refresh() {
    try {
      const res = await fetch('/api/painel-notificacoes', {headers: {'Accept': 'application/json'}, cache: 'no-store'});
      if (!res.ok) return;
      const data = await res.json();
      ['messages','chat','live','pieces_new','reservas','admin_chat','admin_pending'].forEach(k => setCount(k, data[k] || 0));
      dock.classList.toggle('has-any-alert', Number(data.total || data.admin_total || 0) > 0);
    } catch (e) {}
  }

  refresh();
  setInterval(refresh, 15000);

  // Proteção contra clique duplo em formulários e botões críticos.
  document.addEventListener('submit', (ev) => {
    const form = ev.target;
    if (!form || form.dataset.allowDoubleSubmit === '1') return;
    const btn = form.querySelector('button[type="submit"], .btn.primary');
    if (!btn) return;
    if (form.dataset.submitting === '1') {
      ev.preventDefault();
      return;
    }
    form.dataset.submitting = '1';
    btn.dataset.originalText = btn.textContent;
    btn.textContent = 'Enviando...';
    setTimeout(() => {
      form.dataset.submitting = '0';
      if (btn.dataset.originalText) btn.textContent = btn.dataset.originalText;
    }, 7000);
  }, true);

  // Melhor toque nos botões horizontais empilhados da cliente.
  document.querySelectorAll('.brecho-customer-action-stack .btn').forEach(btn => {
    btn.classList.add('wide');
  });
})();