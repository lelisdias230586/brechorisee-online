function brl(value) {
  return Number(value || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("input[type='file']").forEach(input => {
    input.addEventListener("change", () => {
      if (input.files && input.files[0]) {
        input.title = input.files[0].name;
      }
    });
  });

  const menuBtn = document.querySelector("#mobileMenuBtn");
  const sidebar = document.querySelector("#sidebar");
  if (menuBtn && sidebar) {
    menuBtn.addEventListener("click", () => {
      const open = sidebar.classList.toggle("open");
      menuBtn.setAttribute("aria-expanded", open ? "true" : "false");
    });

    sidebar.querySelectorAll("a").forEach(link => {
      link.addEventListener("click", () => {
        sidebar.classList.remove("open");
        menuBtn.setAttribute("aria-expanded", "false");
      });
    });
  }

  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/service-worker.js").catch(() => {});
  }

  let deferredPrompt = null;
  const installButtons = document.querySelectorAll(".install-app-btn");
  window.addEventListener("beforeinstallprompt", event => {
    event.preventDefault();
    deferredPrompt = event;
    installButtons.forEach(btn => btn.hidden = false);
  });
  installButtons.forEach(btn => {
    btn.addEventListener("click", async () => {
      if (!deferredPrompt) return;
      deferredPrompt.prompt();
      await deferredPrompt.userChoice.catch(() => null);
      deferredPrompt = null;
      installButtons.forEach(item => item.hidden = true);
    });
  });
});


/* Preenchimento rápido: listas em cada campo + digitação por voz */
(() => {
  const DEFAULT_SUGGESTIONS = {
    // Títulos precisam ser descritivos. Evita salvar "Casaco Casaco" por toque acidental.
    title: ["Jaqueta jeans","Casaco de lã","Sobretudo jeans","Blusa branca","Vestido floral midi","Calça jeans","Saia midi","Camisa social","Camiseta básica","Body canelado","Regata lisa","Conjunto feminino","Blazer alfaiataria","Tricô inverno","Bolsa transversal","Sandália salto","Tênis casual","Cinto couro","Lenço estampado"],
    category: ["Feminino","Masculino","Infantil","Acessórios","Calçados","Bolsas","Plus size","Vintage","Festa","Praia","Fitness","Jeans"],
    garment_type: ["Bolsa","Calça","Blusa","Vestido","Saia","Short","Macacão","Jaqueta","Casaco","Camisa","Camiseta","Cropped","Body","Regata","Top","Kimono","Conjunto","Colete","Blazer","Moletom","Cardigan","Tricô","Sapato","Sandália","Tênis","Bota","Rasteira","Cinto","Lenço","Óculos","Bijuteria"],
    size: ["PP","P","M","G","GG","XG","Único","34","36","38","40","42","44","46","48","50","52","P/M","M/G","Plus size"],
    brand: ["Sem marca","Farm","Zara","C&A","Renner","Riachuelo","Marisa","Hering","Colcci","Le Lis Blanc","Shoulder","Animale","Maria Filó","Cantão","Arezzo","Schutz","Santa Lolla","Melissa","Adidas","Nike","Puma","Lacoste","Forum","Morena Rosa","Lança Perfume","Dudalina","Youcom","Shein"],
    color: ["Preto","Branco","Off white","Off-white","Bege","Nude","Marrom","Caramelo","Cinza","Azul","Azul-marinho","Jeans","Rosa","Pink","Verde","Verde militar","Vermelho","Vinho","Amarelo","Mostarda","Lilás","Roxo","Laranja","Dourado","Prata"],
    season: ["Verão","Inverno","Meia estação","Primavera","Outono","Festa","Trabalho","Casual","Praia","Academia","Noite","Dia a dia"],
    target_audience: ["Feminino","Masculino","Infantil","Plus size","Jovem","Clássico","Executivo","Vintage","Romântico","Boho","Minimalista","Streetwear","Festa","Gestante"],
    style_tags: ["floral","liso","listrado","poá","animal print","xadrez","geométrico","alfaiataria","oversized","cropped","canelado","renda","bordado","brilho","paetê","couro","jeans","linho","viscose","seda","malha","tricô","cintura alta","wide leg","mom jeans","skinny","pantalona","evasê","midi","longo","curto","com bojo","sem bojo"],
    measurements: ["Busto 90 cm","Cintura 72 cm","Quadril 100 cm","Comprimento 80 cm","Manga 60 cm","Entrepernas 72 cm","Alça regulável","Tamanho único"],
    characteristics: ["floral","liso","estampado","listrado","renda","bordado","botões","zíper","forrado","transparência","elástico","amarrar","manga curta","manga longa","decote V","gola alta","cintura alta","sem avarias","pequeno detalhe","tecido leve","tecido estruturado","ótimo estado"],
    payment_method: ["Dinheiro","Pix","Cartão de débito","Cartão de crédito","Crédito parcelado","Vale","Troca"],
    customer: ["Cliente balcão","Cliente Instagram","Cliente WhatsApp","Retirada loja"],
    notes: ["Consignação","Repasse combinado","Fornecedor prefere Pix","Peças em ótimo estado","Avisar antes de baixar preço"],
    q: ["bolsa preta","vestido floral","calça jeans","blusa branca","Farm floral","jaqueta couro","saia midi","wide leg","plus size","preto P"],
    code: ["BOLSA-001","VESTIDO-001","CALCA-001","BLUSA-001","SAIA-001"],
    codeInput: ["BOLSA-001","VESTIDO-001","CALCA-001","BLUSA-001","SAIA-001"]
  };

  let suggestionsCache = null;
  let activeVoiceTarget = null;
  let voiceCounter = 1;

  function normalizeKey(value) {
    return String(value || "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .trim();
  }

  const GENERIC_TITLE_ONLY = new Set([
    "bolsa","calca","blusa","vestido","saia","short","shorts","macacao","jaqueta",
    "casaco","camisa","camiseta","cropped","body","regata","top","kimono","colete",
    "blazer","moletom","cardigan","trico","sapato","sandalia","tenis","bota","cinto","lenco"
  ]);
  const APPENDABLE_FIELD_KEYS = new Set(["style_tags", "characteristics", "notes", "measurements", "media_notes"]);

  function isGenericTitleOnly(value) {
    return GENERIC_TITLE_ONLY.has(normalizeKey(value));
  }

  function mergeUnique(...groups) {
    const seen = new Set();
    const out = [];
    groups.flat().forEach(item => {
      const text = String(item || "").trim();
      if (!text) return;
      const key = normalizeKey(text);
      if (seen.has(key)) return;
      seen.add(key);
      out.push(text);
    });
    return out;
  }

  function getFieldKey(el) {
    const raw = (el.name || el.id || "").trim();
    if (raw) return raw;
    const ph = normalizeKey(el.placeholder || "");
    if (ph.includes("marca")) return "brand";
    if (ph.includes("cor")) return "color";
    if (ph.includes("tamanho")) return "size";
    if (ph.includes("estampa") || ph.includes("caracter")) return "characteristics";
    if (ph.includes("codigo")) return "code";
    return "";
  }

  function isTextLike(el) {
    if (!el) return false;
    if (el.tagName === "TEXTAREA") return true;
    if (el.tagName !== "INPUT") return false;
    const type = (el.type || "text").toLowerCase();
    return ["text", "search", "tel", "email", "url", "number", ""].includes(type);
  }

  function suggestionsFor(el, all) {
    const key = getFieldKey(el);
    const id = el.id || "";
    const name = el.name || "";
    const placeholder = normalizeKey(el.placeholder || "");
    const groups = [];

    [key, id, name].forEach(k => {
      if (all[k]) groups.push(all[k]);
      if (DEFAULT_SUGGESTIONS[k]) groups.push(DEFAULT_SUGGESTIONS[k]);
    });

    if (id === "cashierSearchInput" || placeholder.includes("tipo, cor") || placeholder.includes("digite codigo")) {
      groups.push(all.search || [], all.q || [], DEFAULT_SUGGESTIONS.q || []);
    }
    if (name === "q" || id.toLowerCase().includes("search")) {
      groups.push(all.q || [], all.search || [], DEFAULT_SUGGESTIONS.q || []);
    }
    if (id === "codeInput" || name === "code") {
      groups.push(all.code || [], all.codeInput || [], DEFAULT_SUGGESTIONS.code || []);
    }
    let merged = mergeUnique(...groups);
    if (key === "title" || name === "title") {
      merged = merged.filter(value => !isGenericTitleOnly(value));
    }
    if (key === "color" || name === "color") {
      merged = merged.filter(value => !["estampado", "colorido"].includes(normalizeKey(value)));
    }
    return merged.slice(0, 160);
  }

  function addDatalist(el, suggestions) {
    if (el.tagName !== "INPUT" || !suggestions.length) return;
    const type = (el.type || "text").toLowerCase();
    if (!["text", "search", "tel", "email", "url", ""].includes(type)) return;
    let listId = el.getAttribute("list");
    if (!listId) {
      listId = `brecho-list-${getFieldKey(el) || el.id || voiceCounter++}`;
      el.setAttribute("list", listId);
    }
    let list = document.getElementById(listId);
    if (!list) {
      list = document.createElement("datalist");
      list.id = listId;
      document.body.appendChild(list);
    }
    list.innerHTML = suggestions.slice(0, 80).map(value => `<option value="${String(value).replace(/"/g, "&quot;")}"></option>`).join("");
  }

  function ensureWrap(el) {
    if (el.closest(".quick-input-wrap")) return el.closest(".quick-input-wrap");
    const wrapper = document.createElement("span");
    wrapper.className = "quick-input-wrap";
    el.parentNode.insertBefore(wrapper, el);
    wrapper.appendChild(el);
    return wrapper;
  }

  function setTextValue(el, text, append = false) {
    if (!el || !text) return;
    const fieldKey = getFieldKey(el);
    const shouldAppend = Boolean(append) && (el.tagName === "TEXTAREA" || APPENDABLE_FIELD_KEYS.has(fieldKey));
    let value = String(text).trim();
    if (!value) return;

    if (shouldAppend && el.value.trim()) {
      const sep = el.value.trim().endsWith(",") ? " " : ", ";
      el.value = `${el.value.trim()}${sep}${value}`;
    } else {
      const start = typeof el.selectionStart === "number" ? el.selectionStart : null;
      const end = typeof el.selectionEnd === "number" ? el.selectionEnd : null;
      if (start !== null && end !== null && start !== end) {
        el.value = el.value.slice(0, start) + value + el.value.slice(end);
      } else if (shouldAppend) {
        el.value = value;
      } else {
        el.value = value;
      }
    }
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    el.focus();
    try { el.setSelectionRange(el.value.length, el.value.length); } catch (err) {}
  }

  function showToast(message) {
    let toast = document.querySelector(".voice-toast");
    if (!toast) {
      toast = document.createElement("div");
      toast.className = "voice-toast";
      document.body.appendChild(toast);
    }
    toast.textContent = message;
    toast.classList.add("show");
    clearTimeout(toast._timer);
    toast._timer = setTimeout(() => toast.classList.remove("show"), 2600);
  }

  function startWebSpeech(el) {
    const Speech = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Speech) {
      el.focus();
      showToast("Toque no microfone do teclado do celular para ditar.");
      return;
    }

    const rec = new Speech();
    rec.lang = "pt-BR";
    rec.interimResults = false;
    rec.maxAlternatives = 1;
    showToast("Ouvindo... fale agora.");
    rec.onresult = event => {
      const text = event.results?.[0]?.[0]?.transcript || "";
      setTextValue(el, text, false);
      showToast("Texto inserido por voz.");
    };
    rec.onerror = () => showToast("Não consegui ouvir. Use o microfone do teclado ou tente de novo.");
    rec.onend = () => {};
    try { rec.start(); } catch (err) { showToast("Não consegui iniciar a voz agora."); }
  }

  function startVoice(el) {
    if (!el.id) {
      el.id = `brecho-voice-target-${voiceCounter++}`;
    }
    activeVoiceTarget = el.id;

    if (window.BRECHORISEE_ANDROID && typeof window.BRECHORISEE_ANDROID.startVoice === "function") {
      try {
        window.BRECHORISEE_ANDROID.startVoice(el.id);
        showToast("Ouvindo pelo Android...");
        return;
      } catch (err) {
        // Continua para a voz do navegador.
      }
    }
    startWebSpeech(el);
  }

  function addVoiceButton(el) {
    if (el.dataset.voiceAttached === "1") return;
    el.dataset.voiceAttached = "1";
    const wrap = ensureWrap(el);
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "voice-input-btn";
    btn.title = "Digitar por voz";
    btn.setAttribute("aria-label", "Digitar por voz");
    btn.textContent = "🎙️";
    btn.addEventListener("click", event => {
      event.preventDefault();
      event.stopPropagation();
      startVoice(el);
    });
    wrap.appendChild(btn);
  }

  function addQuickSuggestions(el, suggestions) {
    if (!suggestions.length || el.dataset.quickSuggestionsAttached === "1") return;
    el.dataset.quickSuggestionsAttached = "1";
    const wrap = ensureWrap(el);

    const box = document.createElement("div");
    box.className = "quick-suggestion-box";
    box.setAttribute("aria-label", "Sugestões rápidas");
    wrap.insertAdjacentElement("afterend", box);

    function render() {
      const term = normalizeKey(el.value || "");
      const filtered = suggestions
        .filter(value => !term || normalizeKey(value).includes(term) || normalizeKey(value).startsWith(term))
        .slice(0, 12);
      const list = filtered.length ? filtered : suggestions.slice(0, 12);
      box.innerHTML = list.map(value => `<button type="button" class="quick-chip">${String(value).replace(/</g, "&lt;").replace(/>/g, "&gt;")}</button>`).join("");
      box.querySelectorAll(".quick-chip").forEach(btn => {
        btn.addEventListener("mousedown", event => event.preventDefault());
        btn.addEventListener("click", event => {
          event.preventDefault();
          const fieldKey = getFieldKey(el);
          const canAppend = el.tagName === "TEXTAREA" || APPENDABLE_FIELD_KEYS.has(fieldKey);
          setTextValue(el, btn.textContent, canAppend);
          box.classList.remove("open");
        });
      });
    }

    el.addEventListener("focus", () => {
      render();
      box.classList.add("open");
    });
    el.addEventListener("input", render);
    el.addEventListener("blur", () => {
      setTimeout(() => box.classList.remove("open"), 160);
    });
  }

  async function loadSuggestions() {
    if (suggestionsCache) return suggestionsCache;
    suggestionsCache = DEFAULT_SUGGESTIONS;
    try {
      const res = await fetch("/api/form-suggestions", { cache: "no-store" });
      const data = await res.json();
      if (data && data.ok && data.suggestions) {
        suggestionsCache = { ...DEFAULT_SUGGESTIONS, ...data.suggestions };
      }
    } catch (err) {
      suggestionsCache = DEFAULT_SUGGESTIONS;
    }
    return suggestionsCache;
  }

  async function enhanceFields() {
    const all = await loadSuggestions();
    document.querySelectorAll("input, textarea").forEach(el => {
      if (!isTextLike(el)) return;
      if (el.closest(".no-quick-fill")) return;

      const type = (el.type || "text").toLowerCase();
      const suggestions = type === "number" ? [] : suggestionsFor(el, all);

      addDatalist(el, suggestions);
      addVoiceButton(el);
      addQuickSuggestions(el, suggestions);
    });

    if (!document.querySelector(".quick-fill-help") && document.querySelector(".mobile-first-form")) {
      const form = document.querySelector(".mobile-first-form");
      const help = document.createElement("div");
      help.className = "quick-fill-help";
      help.innerHTML = "<strong>Preenchimento rápido:</strong> toque em um campo para ver a lista de sugestões ou use 🎙️ para ditar.";
      form.insertBefore(help, form.firstElementChild?.nextSibling || form.firstChild);
    }
  }

  window.BrechoriseeVoice = {
    receiveNativeText(targetId, text) {
      const el = document.getElementById(targetId) || document.getElementById(activeVoiceTarget);
      setTextValue(el, text, false);
      showToast("Texto inserido por voz.");
    }
  };

  document.addEventListener("DOMContentLoaded", enhanceFields);
  if (document.readyState !== "loading") enhanceFields();
})();


/* Busca global em todas as telas: digitação + código/QR + reconhecimento por foto */
(() => {
  function qs(sel) { return document.querySelector(sel); }
  function qsa(sel) { return Array.from(document.querySelectorAll(sel)); }

  function money(value) {
    return Number(value || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
  }

  function productCard(product, score) {
    const img = product.image_filename
      ? `/static/uploads/${product.image_filename}`
      : "";
    const scoreHtml = typeof score === "number"
      ? `<span class="global-score">${score}% parecido</span>`
      : "";
    return `
      <article class="global-result-card">
        <a class="global-result-photo" href="/products/${product.id}">
          ${img ? `<img src="${img}" alt="${product.title || "peça"}">` : `<span>sem foto</span>`}
        </a>
        <div class="global-result-body">
          <strong>${product.title || "Peça"}</strong>
          <small>${product.code || ""} • ${product.garment_type || product.category || "Peça"} • ${product.size || "tam. único"}</small>
          <div class="global-result-meta">
            <b>${money(product.sale_price)}</b>
            <span>${product.status || ""}</span>
            ${scoreHtml}
          </div>
          <div class="inline-actions">
            <a class="btn primary" href="/products/${product.id}">Abrir peça</a>
            <a class="btn ghost" href="/cashier?code=${encodeURIComponent(product.code || "")}">Levar ao caixa</a>
          </div>
        </div>
      </article>
    `;
  }

  function showResults(html) {
    const box = qs("#globalSearchResults");
    if (box) box.innerHTML = html || "";
  }

  async function searchText() {
    const input = qs("#globalSearchInput");
    const status = qs("#globalSearchStatus");
    const q = (input?.value || "").trim();
    if (!q) {
      showResults(`<div class="empty-state compact"><h3>Digite algo para pesquisar.</h3></div>`);
      return;
    }
    showResults(`<p class="hint">Pesquisando...</p>`);
    try {
      const res = await fetch(`/api/products/search?q=${encodeURIComponent(q)}&status=${encodeURIComponent(status?.value || "disponivel")}&limit=30`);
      const data = await res.json();
      const results = data.results || [];
      if (!results.length) {
        showResults(`<div class="empty-state compact"><h3>Nada encontrado.</h3><p>Tente código, marca, cor, tamanho ou característica.</p></div>`);
        return;
      }
      showResults(results.map(p => productCard(p)).join(""));
    } catch (err) {
      showResults(`<div class="empty-state compact"><h3>Erro na busca.</h3><p>Verifique se o servidor está aberto.</p></div>`);
    }
  }

  async function openCode(codeValue) {
    const code = (codeValue || qs("#globalCodeInput")?.value || "").trim().toUpperCase();
    if (!code) return;
    showResults(`<p class="hint">Procurando código ${code}...</p>`);
    try {
      const res = await fetch(`/api/product-by-code?code=${encodeURIComponent(code)}`);
      const data = await res.json();
      if (data.ok && data.product) {
        showResults(productCard(data.product));
        setTimeout(() => { window.location.href = `/products/${data.product.id}`; }, 550);
        return;
      }
      showResults(`<div class="empty-state compact"><h3>Código não encontrado.</h3><p>Você pode tentar pesquisar digitando parte do nome/cor/marca.</p></div>`);
    } catch (err) {
      showResults(`<div class="empty-state compact"><h3>Erro ao abrir código.</h3></div>`);
    }
  }

  async function recognizePhoto(event) {
    event.preventDefault();
    const input = qs("#globalRecognizeInput");
    const hint = qs("#globalRecognizeHint");
    if (!input?.files?.[0]) {
      if (hint) hint.textContent = "Escolha uma foto primeiro.";
      return;
    }
    const formData = new FormData();
    formData.append("image", input.files[0]);
    showResults(`<p class="hint">Reconhecendo pela foto...</p>`);
    try {
      const res = await fetch("/api/recognize", { method: "POST", body: formData });
      const data = await res.json();
      const results = data.results || [];
      if (!results.length) {
        showResults(`<div class="empty-state compact"><h3>Nenhuma peça parecida encontrada.</h3><p>Tente outra foto com melhor luz ou enquadramento.</p></div>`);
        return;
      }
      showResults(results.map(p => productCard(p, p.score)).join(""));
    } catch (err) {
      showResults(`<div class="empty-state compact"><h3>Erro no reconhecimento.</h3><p>Tente novamente.</p></div>`);
    }
  }

  function setTab(name) {
    qsa("[data-global-tab]").forEach(btn => btn.classList.toggle("primary", btn.dataset.globalTab === name));
    qsa("[data-global-panel]").forEach(panel => panel.hidden = panel.dataset.globalPanel !== name);
    if (name !== "barcode") {
      const video = qs("#globalBarcodeVideo");
      window.BrechoriseeCamera?.stopBarcodeScanner?.(video);
    }
  }

  function openModal() {
    const modal = qs("#globalSearchModal");
    if (!modal) return;
    modal.hidden = false;
    document.body.classList.add("global-search-open");
    setTimeout(() => qs("#globalSearchInput")?.focus(), 80);
  }

  function closeModal() {
    const modal = qs("#globalSearchModal");
    if (!modal) return;
    modal.hidden = true;
    document.body.classList.remove("global-search-open");
    const video = qs("#globalBarcodeVideo");
    window.BrechoriseeCamera?.stopBarcodeScanner?.(video);
  }

  document.addEventListener("DOMContentLoaded", () => {
    qsa(".global-search-btn").forEach(btn => btn.addEventListener("click", openModal));
    qsa("[data-close-global-search]").forEach(el => el.addEventListener("click", closeModal));
    qsa("[data-global-tab]").forEach(btn => btn.addEventListener("click", () => setTab(btn.dataset.globalTab)));

    qs("#globalSearchDoBtn")?.addEventListener("click", searchText);
    qs("#globalSearchInput")?.addEventListener("keydown", event => {
      if (event.key === "Enter") {
        event.preventDefault();
        searchText();
      }
    });

    qs("#globalOpenCodeBtn")?.addEventListener("click", () => openCode());
    qs("#globalCodeInput")?.addEventListener("keydown", event => {
      if (event.key === "Enter") {
        event.preventDefault();
        openCode();
      }
    });

    qs("#globalBarcodeStartBtn")?.addEventListener("click", async () => {
      const video = qs("#globalBarcodeVideo");
      const hint = qs("#globalBarcodeHint");
      const ok = await window.BrechoriseeCamera?.startBarcodeScanner?.({
        video,
        hint,
        onCode: (code) => {
          const input = qs("#globalCodeInput");
          if (input) input.value = code;
          window.BrechoriseeCamera?.stopBarcodeScanner?.(video);
          openCode(code);
        }
      });
      if (!ok && hint) hint.textContent = "Câmera ao vivo indisponível. Digite o código ou use reconhecimento por foto.";
    });
    qs("#globalBarcodeStopBtn")?.addEventListener("click", () => {
      window.BrechoriseeCamera?.stopBarcodeScanner?.(qs("#globalBarcodeVideo"));
    });

    qs("#globalRecognizeForm")?.addEventListener("submit", recognizePhoto);
  });
})();


// Camada profissional: reduz envio duplo em formulários críticos e melhora operação por teclado.
document.addEventListener("submit", event => {
  const form = event.target;
  if (!(form instanceof HTMLFormElement)) return;
  if (event.defaultPrevented) return;
  if (form.dataset.allowDoubleSubmit === "true") return;
  if (form.dataset.submitted === "true") {
    event.preventDefault();
    return;
  }
  form.dataset.submitted = "true";
  form.dataset.loading = "true";
  const submitter = event.submitter;
  if (submitter && submitter instanceof HTMLButtonElement) {
    submitter.dataset.originalText = submitter.textContent || "";
    submitter.textContent = submitter.dataset.loadingText || "Processando...";
    submitter.disabled = true;
  }
});

document.addEventListener("keydown", event => {
  if (event.key !== "Escape") return;
  document.querySelectorAll(".sidebar.open").forEach(element => element.classList.remove("open"));
  document.querySelectorAll("[aria-expanded='true']").forEach(element => element.setAttribute("aria-expanded", "false"));
  document.querySelectorAll(".global-search-overlay:not([hidden])").forEach(element => element.hidden = true);
});
