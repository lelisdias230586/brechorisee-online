const cart = new Map();
let stream = null;
let scanTimer = null;
let cashierSearchDebounce = null;
let pendingPaymentPayload = null;
const PAYMENT_SETTINGS_KEY = "brechorisee_payment_app_settings";

const $ = (sel) => document.querySelector(sel);

function imgSrc(product) {
  return product.image_filename ? `/static/uploads/${product.image_filename}` : "";
}

function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function productThumb(product, sizeClass = "") {
  if (product.image_filename) {
    return `<img class="${sizeClass}" src="${imgSrc(product)}" alt="${esc(product.title)}">`;
  }
  return `<div class="cart-thumb ${sizeClass}">sem foto</div>`;
}

function miniProductResult(product, options = {}) {
  const scoreText = product.score ? `${esc(product.score)}% • ` : "";
  const details = [
    product.code,
    product.garment_type || product.category || "peça",
    product.size || "tam. único",
    product.color || ""
  ].filter(Boolean).join(" • ");
  const alreadyInCart = cart.has(product.code);
  const buttonText = alreadyInCart ? "Já no carrinho" : (options.buttonText || "Adicionar");
  return `
    <div class="mini-result">
      ${productThumb(product)}
      <div>
        <strong>${esc(product.title)}</strong>
        <small>${scoreText}${esc(details)} • ${brl(product.sale_price)}</small>
      </div>
      <button class="btn ${alreadyInCart ? "ghost" : "primary"}" type="button" data-add-code="${esc(product.code)}" ${alreadyInCart ? "disabled" : ""}>${buttonText}</button>
    </div>
  `;
}

function bindAddButtons(box) {
  box.querySelectorAll("[data-add-code]").forEach(button => {
    button.addEventListener("click", async () => {
      await addCode(button.dataset.addCode);
      button.textContent = "Adicionado";
      button.disabled = true;
      button.classList.remove("primary");
      button.classList.add("ghost");
    });
  });
}

function renderCart() {
  const box = $("#cartItems");
  const items = Array.from(cart.values());
  const countBadge = $("#cartCountBadge");
  if (countBadge) {
    countBadge.textContent = `${items.length} ${items.length === 1 ? "peça" : "peças"}`;
  }

  if (!items.length) {
    box.className = "cart-items empty";
    box.textContent = "Nenhuma peça adicionada.";
  } else {
    box.className = "cart-items";
    box.innerHTML = items.map((product, index) => `
      <div class="cart-item">
        ${productThumb(product)}
        <div>
          <strong>${index + 1}. ${esc(product.title)}</strong>
          <small>${esc(product.code)} • ${esc(product.garment_type || "-")} • ${esc(product.size || "-")}</small>
          <div>${brl(product.sale_price)}</div>
        </div>
        <button class="btn ghost" type="button" onclick="removeFromCart('${esc(product.code)}')">Remover</button>
      </div>
    `).join("");
  }

  updateTotals();
}

function updateTotals() {
  const subtotal = Array.from(cart.values()).reduce((sum, product) => sum + Number(product.sale_price || 0), 0);
  const discount = Number($("#discountInput").value || 0);
  const paid = Number($("#paidInput").value || 0);
  const total = Math.max(0, subtotal - discount);
  const change = Math.max(0, paid - total);

  $("#subtotalText").textContent = brl(subtotal);
  $("#totalText").textContent = brl(total);
  $("#changeText").textContent = brl(change);
}

async function addCode(code) {
  const normalized = String(code || "").trim().toUpperCase();
  const message = $("#checkoutMessage");
  message.textContent = "";

  if (!normalized) return false;

  if (cart.has(normalized)) {
    message.textContent = "Essa peça já está no carrinho.";
    return false;
  }

  try {
    const res = await fetch(`/api/product-by-code?code=${encodeURIComponent(normalized)}`);
    const data = await res.json();

    if (!res.ok || !data.ok) {
      message.textContent = data.message || "Peça não encontrada.";
      return false;
    }

    if (data.product.status !== "disponivel") {
      message.textContent = `Peça ${data.product.code} está com status: ${data.product.status}.`;
      return false;
    }

    cart.set(data.product.code, data.product);
    $("#codeInput").value = "";
    renderCart();
    return true;
  } catch (err) {
    message.textContent = "Não foi possível adicionar a peça.";
    return false;
  }
}

async function addMultipleCodes(rawText) {
  const message = $("#checkoutMessage");
  const text = String(rawText || "").trim().toUpperCase();
  if (!text) {
    if (message) message.textContent = "Digite ou cole os códigos das peças.";
    return;
  }

  const codes = text
    .split(/[\n,;\t ]+/)
    .map(code => code.trim())
    .filter(Boolean);

  if (!codes.length) {
    if (message) message.textContent = "Nenhum código válido na lista.";
    return;
  }

  let added = 0;
  let skipped = 0;
  const failures = [];

  for (const code of codes) {
    const before = cart.size;
    const ok = await addCode(code);
    if (ok && cart.size > before) {
      added += 1;
    } else {
      skipped += 1;
      if (!cart.has(code)) failures.push(code);
    }
  }

  renderCart();

  if (message) {
    const parts = [`${added} ${added === 1 ? "peça adicionada" : "peças adicionadas"} ao carrinho`];
    if (skipped) parts.push(`${skipped} ${skipped === 1 ? "item ignorado" : "itens ignorados"}`);
    if (failures.length) parts.push(`não encontrados/indisponíveis: ${failures.slice(0, 8).join(", ")}${failures.length > 8 ? "..." : ""}`);
    message.textContent = parts.join(". ") + ".";
  }

  const bulkInput = $("#bulkCodesInput");
  if (bulkInput && added) bulkInput.value = "";
}

window.addMultipleCodes = addMultipleCodes;

window.addCode = addCode;

window.removeFromCart = function(code) {
  cart.delete(code);
  renderCart();
};


function subtotalFromCart() {
  return Array.from(cart.values()).reduce((sum, product) => sum + Number(product.sale_price || 0), 0);
}

function currentTotal() {
  const subtotal = subtotalFromCart();
  const discount = Number($("#discountInput").value || 0);
  return Math.max(0, subtotal - discount);
}

function buildCheckoutPayload() {
  const total = currentTotal();
  const paymentMethod = $("#paymentInput").value;
  let paid = Number($("#paidInput").value || 0);

  if (!paymentMethod.toLowerCase().includes("dinheiro") && paid <= 0) {
    paid = total;
    $("#paidInput").value = total.toFixed(2);
    updateTotals();
  }

  return {
    codes: Array.from(cart.keys()),
    customer: $("#customerInput").value,
    payment_method: paymentMethod,
    discount: Number($("#discountInput").value || 0),
    paid
  };
}

function getPaymentSettings() {
  const defaults = {
    enabled: true,
    packageName: "",
    deeplink: ""
  };

  try {
    const saved = JSON.parse(localStorage.getItem(PAYMENT_SETTINGS_KEY) || "{}");
    return { ...defaults, ...saved };
  } catch (err) {
    return defaults;
  }
}

function savePaymentSettings() {
  const settings = {
    enabled: Boolean($("#paymentAppEnabled")?.checked),
    packageName: String($("#paymentAppPackage")?.value || "").trim(),
    deeplink: String($("#paymentAppDeeplink")?.value || "").trim()
  };

  localStorage.setItem(PAYMENT_SETTINGS_KEY, JSON.stringify(settings));
  const message = $("#checkoutMessage");
  if (message) message.textContent = "Configuração da maquininha salva.";
  return settings;
}

function chooseInstalledPaymentApp() {
  const message = $("#checkoutMessage");
  if (!window.BRECHORISEE_ANDROID || typeof window.BRECHORISEE_ANDROID.choosePaymentApp !== "function") {
    if (message) message.textContent = "A escolha automática do app instalado funciona dentro do app Android.";
    return;
  }
  window.BRECHORISEE_ANDROID.choosePaymentApp();
}

function loadPaymentSettings() {
  const settings = getPaymentSettings();
  if ($("#paymentAppEnabled")) $("#paymentAppEnabled").checked = Boolean(settings.enabled);
  if ($("#paymentAppPackage")) $("#paymentAppPackage").value = settings.packageName || "";
  if ($("#paymentAppDeeplink")) $("#paymentAppDeeplink").value = settings.deeplink || "";
}

function shouldOpenPaymentApp(payload) {
  const enabled = Boolean($("#paymentAppEnabled")?.checked);
  if (!enabled) return false;

  const method = String(payload.payment_method || "").toLowerCase();
  if (method.includes("dinheiro")) return false;

  return true;
}

function showPaymentPendingBox(show) {
  const box = $("#paymentPendingBox");
  if (box) box.hidden = !show;
}

function referenceForPayment() {
  const firstCode = Array.from(cart.keys())[0] || "VENDA";
  return `BRECHORISEE-${firstCode}-${Date.now()}`;
}

function openNativePaymentApp(payload, options = {}) {
  const message = $("#checkoutMessage");
  const settings = savePaymentSettings();
  const total = currentTotal();
  const reference = options.reference || referenceForPayment();

  if (!window.BRECHORISEE_ANDROID || typeof window.BRECHORISEE_ANDROID.openPaymentApp !== "function") {
    message.textContent = "A abertura automática da maquininha funciona dentro do app Android. No navegador, finalize manualmente.";
    return false;
  }

  if (!settings.packageName && !settings.deeplink) {
    message.textContent = "Configure o pacote do app da maquininha ou o link/deeplink antes de usar.";
    $("#paymentAppSettings")?.setAttribute("open", "open");
    return false;
  }

  try {
    window.BRECHORISEE_ANDROID.openPaymentApp(
      total.toFixed(2),
      String(payload.payment_method || ""),
      reference,
      settings.packageName || "",
      settings.deeplink || ""
    );
    message.innerHTML = `Abrindo maquininha para <strong>${brl(total)}</strong>. A venda ainda não foi salva.`;
    return true;
  } catch (err) {
    message.textContent = "Não consegui chamar o app da maquininha.";
    return false;
  }
}

async function saveCheckout(payload) {
  const message = $("#checkoutMessage");
  const checkoutBtn = $("#checkoutBtn");
  const confirmBtn = $("#confirmPaymentBtn");

  message.textContent = "";
  if (checkoutBtn) checkoutBtn.disabled = true;
  if (confirmBtn) confirmBtn.disabled = true;

  try {
    const res = await fetch("/api/checkout", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json();

    if (!res.ok || !data.ok) {
      message.textContent = data.message || "Não foi possível finalizar.";
      return false;
    }

    message.innerHTML = `Venda <strong>${esc(data.sale_code)}</strong> finalizada. Total ${brl(data.total)}. Troco ${brl(data.change)}. Peças retiradas do estoque disponível.`;
    pendingPaymentPayload = null;
    showPaymentPendingBox(false);
    cart.clear();
    renderCart();
    $("#discountInput").value = 0;
    $("#paidInput").value = 0;
    const searchResults = $("#cashierSearchResults");
    if (searchResults) searchResults.innerHTML = "";
    return true;
  } catch (err) {
    message.textContent = "Erro ao finalizar a venda.";
    return false;
  } finally {
    if (checkoutBtn) checkoutBtn.disabled = false;
    if (confirmBtn) confirmBtn.disabled = false;
  }
}

async function finishCheckout() {
  const message = $("#checkoutMessage");
  message.textContent = "";

  const payload = buildCheckoutPayload();

  if (!payload.codes.length) {
    message.textContent = "Carrinho vazio.";
    return;
  }

  if (shouldOpenPaymentApp(payload)) {
    const opened = openNativePaymentApp(payload);
    if (opened) {
      pendingPaymentPayload = payload;
      showPaymentPendingBox(true);
    }
    return;
  }

  await saveCheckout(payload);
}

window.BrechoriseePayment = {
  receiveSelectedPaymentApp(packageName, label) {
    if ($("#paymentAppPackage")) $("#paymentAppPackage").value = packageName || "";
    savePaymentSettings();
    const msg = $("#checkoutMessage");
    if (msg) msg.textContent = label ? `App selecionado: ${label}` : "App da maquininha selecionado.";
  },

  paymentAppOpenResult(ok, message) {
    const msg = $("#checkoutMessage");
    if (!ok) {
      if (msg) msg.textContent = message || "Não foi possível abrir o app da maquininha.";
      pendingPaymentPayload = null;
      showPaymentPendingBox(false);
      return;
    }
    if (msg && message) msg.textContent = message;
  },

  returnedFromPaymentApp() {
    if (pendingPaymentPayload) {
      showPaymentPendingBox(true);
      const msg = $("#checkoutMessage");
      if (msg) msg.textContent = "Você voltou da maquininha. Confirme somente se o pagamento foi aprovado.";
    }
  },

  receiveExternalPaymentStatus(status, rawUri) {
    const normalized = String(status || "").toLowerCase();
    const approved = ["approved", "aprovado", "paid", "pago", "success", "sucesso", "confirmed", "confirmado"].includes(normalized);
    const msg = $("#checkoutMessage");

    if (approved && pendingPaymentPayload) {
      if (msg) msg.textContent = "Pagamento aprovado pela maquininha. Salvando venda...";
      saveCheckout(pendingPaymentPayload);
      return;
    }

    if (msg) msg.textContent = `Retorno da maquininha recebido: ${status || rawUri || "sem status"}. Confirme manualmente se foi aprovado.`;
    showPaymentPendingBox(Boolean(pendingPaymentPayload));
  }
};

async function startQrScan() {
  const hint = $("#scanHint");
  const video = $("#qrVideo");

  if (window.BrechoriseeCamera) {
    await window.BrechoriseeCamera.startBarcodeScanner({
      video,
      hint,
      onCode: async (value) => {
        await addCode(value);
      }
    });
    return;
  }

  hint.textContent = "Leitor de câmera não carregado. Use o código digitado, busca digitada ou reconhecimento por foto.";
}

function stopQrScan() {
  const video = $("#qrVideo");
  if (window.BrechoriseeCamera) {
    window.BrechoriseeCamera.stopBarcodeScanner(video);
    return;
  }
  if (scanTimer) clearInterval(scanTimer);
  scanTimer = null;
  if (stream) stream.getTracks().forEach(track => track.stop());
  stream = null;
  video.style.display = "none";
}

async function searchProductsForCashier() {
  const input = $("#cashierSearchInput");
  const resultsBox = $("#cashierSearchResults");
  const q = String(input?.value || "").trim();

  if (!resultsBox) return;
  resultsBox.innerHTML = "";

  if (q.length < 2) {
    resultsBox.innerHTML = `<p class="hint">Digite pelo menos 2 letras ou números para pesquisar.</p>`;
    return;
  }

  resultsBox.innerHTML = `<p class="hint">Pesquisando por “${esc(q)}”...</p>`;

  try {
    const res = await fetch(`/api/products/search?q=${encodeURIComponent(q)}&status=disponivel&limit=12`);
    const data = await res.json();

    if (!res.ok || !data.ok) {
      resultsBox.innerHTML = `<p class="hint">${esc(data.message || "Não foi possível pesquisar.")}</p>`;
      return;
    }

    if (!data.results.length) {
      resultsBox.innerHTML = `<p class="hint">Nenhuma peça disponível encontrada. Tente outra palavra, cor, tamanho, marca ou código.</p>`;
      return;
    }

    resultsBox.innerHTML = data.results.map(product => miniProductResult(product, { buttonText: "Adicionar" })).join("");
    bindAddButtons(resultsBox);
  } catch (err) {
    resultsBox.innerHTML = `<p class="hint">Erro ao pesquisar. Confira se o sistema está aberto no computador.</p>`;
  }
}

async function recognizeForCashier() {
  const input = $("#cashierImage");
  const resultsBox = $("#cashierRecognitionResults");
  resultsBox.innerHTML = "";

  if (!input.files || !input.files[0]) {
    resultsBox.textContent = "Escolha uma foto para pesquisar.";
    return;
  }

  const formData = new FormData();
  formData.append("image", input.files[0]);

  resultsBox.textContent = "Pesquisando peças parecidas...";

  try {
    const res = await fetch("/api/recognize", { method: "POST", body: formData });
    const data = await res.json();

    if (!res.ok || !data.ok || !data.results.length) {
      resultsBox.textContent = data.message || "Nenhum resultado.";
      return;
    }

    resultsBox.innerHTML = data.results.map(product => miniProductResult(product, { buttonText: "Adicionar" })).join("");
    bindAddButtons(resultsBox);
  } catch (err) {
    resultsBox.textContent = "Erro ao pesquisar a imagem.";
  }
}

document.addEventListener("DOMContentLoaded", () => {

  loadPaymentSettings();

  $("#choosePaymentAppBtn")?.addEventListener("click", chooseInstalledPaymentApp);
  $("#savePaymentAppSettingsBtn")?.addEventListener("click", savePaymentSettings);
  $("#paymentAppEnabled")?.addEventListener("change", savePaymentSettings);
  $("#paymentAppPackage")?.addEventListener("change", savePaymentSettings);
  $("#paymentAppDeeplink")?.addEventListener("change", savePaymentSettings);
  $("#testPaymentAppBtn")?.addEventListener("click", () => {
    const payload = buildCheckoutPayload();
    const opened = openNativePaymentApp(payload, { reference: "TESTE-BRECHORISEE" });
    if (opened) {
      $("#checkoutMessage").textContent = "Teste enviado. Se o app da maquininha abriu, a configuração está funcionando.";
    }
  });
  $("#confirmPaymentBtn")?.addEventListener("click", async () => {
    if (!pendingPaymentPayload) {
      $("#checkoutMessage").textContent = "Nenhuma venda aguardando confirmação.";
      return;
    }
    await saveCheckout(pendingPaymentPayload);
  });
  $("#cancelPaymentBtn")?.addEventListener("click", () => {
    pendingPaymentPayload = null;
    showPaymentPendingBox(false);
    $("#checkoutMessage").textContent = "Pagamento cancelado. A venda não foi salva e o estoque não foi baixado.";
  });
  $("#addCodeBtn").addEventListener("click", () => addCode($("#codeInput").value));
  $("#codeInput").addEventListener("keydown", event => {
    if (event.key === "Enter") addCode($("#codeInput").value);
  });
  $("#addBulkCodesBtn")?.addEventListener("click", () => addMultipleCodes($("#bulkCodesInput")?.value));
  $("#clearBulkCodesBtn")?.addEventListener("click", () => {
    if ($("#bulkCodesInput")) $("#bulkCodesInput").value = "";
  });
  $("#bulkCodesInput")?.addEventListener("keydown", event => {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
      addMultipleCodes($("#bulkCodesInput")?.value);
    }
  });

  const cashierSearchInput = $("#cashierSearchInput");
  const cashierSearchBtn = $("#cashierSearchBtn");
  cashierSearchBtn?.addEventListener("click", searchProductsForCashier);
  cashierSearchInput?.addEventListener("keydown", event => {
    if (event.key === "Enter") {
      event.preventDefault();
      searchProductsForCashier();
    }
  });
  cashierSearchInput?.addEventListener("input", () => {
    clearTimeout(cashierSearchDebounce);
    const value = cashierSearchInput.value.trim();
    if (value.length < 2) {
      $("#cashierSearchResults").innerHTML = "";
      return;
    }
    cashierSearchDebounce = setTimeout(searchProductsForCashier, 350);
  });

  $("#discountInput").addEventListener("input", updateTotals);
  $("#paidInput").addEventListener("input", updateTotals);
  $("#checkoutBtn").addEventListener("click", finishCheckout);
  $("#clearCartBtn").addEventListener("click", () => { cart.clear(); renderCart(); });
  $("#startScanBtn").addEventListener("click", startQrScan);
  $("#stopScanBtn").addEventListener("click", stopQrScan);
  $("#cashierRecognizeBtn").addEventListener("click", recognizeForCashier);
  renderCart();
});
