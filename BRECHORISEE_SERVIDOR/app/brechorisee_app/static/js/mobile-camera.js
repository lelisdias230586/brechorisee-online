(() => {
  let stream = null;
  let scanTimer = null;
  let detector = null;

  function setHint(hint, message) {
    if (hint) hint.textContent = message;
  }

  function stopBarcodeScanner(video) {
    if (scanTimer) clearInterval(scanTimer);
    scanTimer = null;
    if (stream) stream.getTracks().forEach(track => track.stop());
    stream = null;
    if (video) {
      video.pause?.();
      video.srcObject = null;
      video.style.display = "none";
    }
  }

  async function startBarcodeScanner({ video, hint, onCode }) {
    if (!video) return false;

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setHint(hint, "Este navegador não liberou câmera ao vivo. Use foto, código digitado ou pesquise manualmente.");
      return false;
    }

    if (!("BarcodeDetector" in window)) {
      setHint(hint, "Este navegador não possui leitor nativo de QR/código. Use o código digitado ou reconhecimento por foto.");
      return false;
    }

    try {
      detector = new BarcodeDetector({ formats: ["qr_code", "code_128", "code_39", "ean_13", "ean_8", "upc_a", "upc_e"] });
      stopBarcodeScanner(video);
      stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: { ideal: "environment" },
          width: { ideal: 1280 },
          height: { ideal: 720 }
        },
        audio: false
      });
      video.srcObject = stream;
      video.style.display = "block";
      video.setAttribute("playsinline", "true");
      video.muted = true;
      await video.play();
      setHint(hint, "Câmera ligada. Aponte para o QR Code ou código da etiqueta.");

      let lastValue = "";
      scanTimer = setInterval(async () => {
        try {
          const codes = await detector.detect(video);
          if (!codes.length) return;
          const value = String(codes[0].rawValue || "").trim();
          if (!value || value === lastValue) return;
          lastValue = value;
          setHint(hint, `Código lido: ${value}`);
          if (typeof onCode === "function") onCode(value);
        } catch (err) {
          // Ignora frames que o navegador não consegue processar.
        }
      }, 650);
      return true;
    } catch (err) {
      setHint(hint, "Não consegui acessar a câmera ao vivo. Verifique permissão, Wi‑Fi e navegador. Você ainda pode usar foto ou código digitado.");
      stopBarcodeScanner(video);
      return false;
    }
  }


  function updateSelectedLabel(input, count) {
    const card = input.closest(".camera-card");
    const title = card ? card.querySelector(".camera-card-title") : null;
    if (!title) return;
    if (!title.dataset.originalText) title.dataset.originalText = title.textContent;
    if (count > 0) {
      title.textContent = `${title.dataset.originalText} • ${count} arquivo(s) selecionado(s)`;
    } else {
      title.textContent = title.dataset.originalText;
    }
  }

  function previewPhotoInput(input) {
    const selector = input.getAttribute("data-preview");
    const img = selector ? document.querySelector(selector) : null;
    updateSelectedLabel(input, input.files ? input.files.length : 0);
    if (!img || !input.files || !input.files[0]) return;
    const file = input.files[0];
    if (!file.type || !file.type.startsWith("image/")) return;

    const reader = new FileReader();
    reader.onload = event => {
      img.src = event.target.result;
      img.hidden = false;
    };
    reader.readAsDataURL(file);
  }

  function previewMediaInput(input) {
    const selector = input.getAttribute("data-preview-list");
    const box = selector ? document.querySelector(selector) : null;
    if (!box) return;
    box.innerHTML = "";

    const files = Array.from(input.files || []);
    updateSelectedLabel(input, files.length);
    if (!files.length) {
      box.innerHTML = "<small>Nenhum arquivo selecionado.</small>";
      return;
    }

    files.slice(0, 12).forEach(file => {
      const tile = document.createElement("div");
      tile.className = "media-preview-tile";

      const name = document.createElement("small");
      name.textContent = file.name || "arquivo";

      if (file.type && file.type.startsWith("image/")) {
        const img = document.createElement("img");
        img.alt = file.name || "foto";
        const reader = new FileReader();
        reader.onload = event => { img.src = event.target.result; };
        reader.readAsDataURL(file);
        tile.appendChild(img);
      } else if (file.type && file.type.startsWith("video/")) {
        const video = document.createElement("video");
        video.controls = true;
        video.preload = "metadata";
        video.src = URL.createObjectURL(file);
        tile.appendChild(video);
      } else {
        const icon = document.createElement("div");
        icon.className = "file-placeholder";
        icon.textContent = "📎";
        tile.appendChild(icon);
      }

      tile.appendChild(name);
      box.appendChild(tile);
    });

    if (files.length > 12) {
      const more = document.createElement("small");
      more.textContent = `+ ${files.length - 12} arquivo(s) selecionado(s).`;
      box.appendChild(more);
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    const productForm = document.querySelector("#productForm");
    if (productForm) {
      productForm.addEventListener("submit", () => {
        const submitBtn = productForm.querySelector("button[type='submit']");
        if (submitBtn) {
          submitBtn.disabled = true;
          submitBtn.textContent = "Salvando peça e arquivos...";
        }
      });
    }

    document.querySelectorAll(".mobile-photo-input").forEach(input => {
      input.addEventListener("change", () => previewPhotoInput(input));
    });
    document.querySelectorAll(".mobile-media-input").forEach(input => {
      input.addEventListener("change", () => previewMediaInput(input));
    });
  });

  window.BrechoriseeCamera = {
    startBarcodeScanner,
    stopBarcodeScanner,
    previewPhotoInput,
    previewMediaInput
  };
})();
