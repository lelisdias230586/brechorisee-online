
(function() {
  const STORAGE_KEY = "brechorisee_online_cart";

  function readCart() {
    try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]"); }
    catch (e) { return []; }
  }
  function writeCart(cart) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(cart));
    updateCount();
  }
  function money(value) {
    const n = Number(value || 0);
    return n.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
  }
  function updateCount() {
    const cart = readCart();
    document.querySelectorAll("[data-cart-count]").forEach(el => el.textContent = cart.length);
  }
  function addItem(item) {
    const cart = readCart();
    if (cart.some(x => x.code === item.code)) {
      alert("Essa peça já está no carrinho.");
      return;
    }
    cart.push(item);
    writeCart(cart);
    alert("Peça adicionada ao carrinho.");
  }

  document.addEventListener("click", (ev) => {
    const btn = ev.target.closest(".add-to-cart-btn");
    if (!btn) return;
    addItem({
      code: btn.dataset.code,
      title: btn.dataset.title,
      price: Number(btn.dataset.price || 0),
      photo: btn.dataset.photo || ""
    });
  });

  function renderCartPage() {
    const container = document.getElementById("cartItems");
    const totalEl = document.getElementById("cartTotal");
    const codesEl = document.getElementById("cartCodes");
    const form = document.getElementById("checkoutForm");
    if (!container) return;
    const cart = readCart();
    if (!cart.length) {
      container.innerHTML = `<div class="empty-state compact"><h3>Carrinho vazio.</h3><p>Volte para a vitrine e escolha suas peças.</p><a class="btn primary" href="/loja">Abrir vitrine</a></div>`;
      if (form) form.style.display = "none";
      if (totalEl) totalEl.textContent = money(0);
      return;
    }
    const total = cart.reduce((sum, item) => sum + Number(item.price || 0), 0);
    container.innerHTML = cart.map((item, idx) => `
      <article class="cart-item">
        ${item.photo ? `<img src="${item.photo}" alt="${item.title || item.code}">` : ""}
        <div>
          <strong>${item.title || item.code}</strong>
          <small>${item.code}</small>
          <b>${money(item.price)}</b>
        </div>
        <button class="btn ghost remove-cart-item" type="button" data-index="${idx}">Remover</button>
      </article>
    `).join("");
    if (totalEl) totalEl.textContent = money(total);
    if (codesEl) codesEl.value = cart.map(x => x.code).join(",");
  }

  document.addEventListener("click", (ev) => {
    const btn = ev.target.closest(".remove-cart-item");
    if (!btn) return;
    const cart = readCart();
    cart.splice(Number(btn.dataset.index), 1);
    writeCart(cart);
    renderCartPage();
  });

  document.addEventListener("submit", (ev) => {
    const form = ev.target.closest("#checkoutForm");
    if (!form) return;
    const cart = readCart();
    if (!cart.length) {
      ev.preventDefault();
      alert("Carrinho vazio.");
      return;
    }
    const codesEl = document.getElementById("cartCodes");
    if (codesEl) codesEl.value = cart.map(x => x.code).join(",");
    setTimeout(() => localStorage.removeItem(STORAGE_KEY), 500);
  });

  updateCount();
  renderCartPage();
})();
