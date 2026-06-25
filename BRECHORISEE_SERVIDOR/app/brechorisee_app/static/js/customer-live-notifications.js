(function () {
  const CHECK_EVERY_MS = 25000;
  const STORAGE_KEY = "brechorisee_last_live_notification_id";

  function isCustomerArea() {
    return location.pathname.startsWith("/cliente");
  }

  async function ensurePermission() {
    if (!("Notification" in window)) return false;
    if (Notification.permission === "granted") return true;
    if (Notification.permission === "denied") return false;
    try {
      const result = await Notification.requestPermission();
      return result === "granted";
    } catch (e) {
      return false;
    }
  }

  function openLive(notificationId) {
    if (notificationId) {
      fetch(`/api/cliente/notificacoes/${notificationId}/lida`, {
        method: "POST",
        credentials: "same-origin"
      }).catch(() => {});
    }
    location.href = "/cliente/live";
  }

  async function showLiveNotification(n) {
    if (!n || !n.id) return;
    const last = localStorage.getItem(STORAGE_KEY);
    if (String(last) === String(n.id)) return;
    localStorage.setItem(STORAGE_KEY, String(n.id));

    const ok = await ensurePermission();
    if (!ok) {
      // Sem permissão de notificação, abre um aviso visual dentro do app.
      const banner = document.createElement("button");
      banner.type = "button";
      banner.textContent = "✨ Live BRECHORISEE começou — tocar para entrar";
      banner.style.position = "fixed";
      banner.style.left = "12px";
      banner.style.right = "12px";
      banner.style.bottom = "calc(14px + env(safe-area-inset-bottom))";
      banner.style.zIndex = "99999";
      banner.style.border = "0";
      banner.style.borderRadius = "18px";
      banner.style.padding = "16px";
      banner.style.fontWeight = "800";
      banner.style.background = "#a84d3a";
      banner.style.color = "#fff";
      banner.style.boxShadow = "0 12px 28px rgba(0,0,0,.2)";
      banner.addEventListener("click", () => openLive(n.id));
      document.body.appendChild(banner);
      setTimeout(() => banner.remove(), 16000);
      return;
    }

    const title = n.title || "BRECHORISEE ao vivo agora ✨";
    const options = {
      body: n.message || "Toque para entrar direto na live.",
      tag: `brechorisee-live-${n.live_session_id || n.id}`,
      renotify: true,
      data: { url: "/cliente/live", notificationId: n.id },
      icon: "/static/icons/icon-192.png",
      badge: "/static/icons/icon-192.png"
    };

    try {
      if ("serviceWorker" in navigator) {
        const reg = await navigator.serviceWorker.ready;
        await reg.showNotification(title, options);
      } else {
        const notification = new Notification(title, options);
        notification.onclick = () => {
          window.focus();
          openLive(n.id);
        };
      }
    } catch (e) {
      const notification = new Notification(title, options);
      notification.onclick = () => {
        window.focus();
        openLive(n.id);
      };
    }
  }

  async function checkLiveAlert() {
    if (!isCustomerArea()) return;
    try {
      const res = await fetch("/api/cliente/notificacoes/live-alert", {
        credentials: "same-origin",
        headers: { "Accept": "application/json" }
      });
      if (!res.ok) return;
      const data = await res.json();
      if (data && data.notification) {
        await showLiveNotification(data.notification);
      }
    } catch (e) {}
  }

  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/service-worker.js").catch(() => {});
  }

  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) checkLiveAlert();
  });

  window.addEventListener("focus", checkLiveAlert);
  document.addEventListener("DOMContentLoaded", () => {
    checkLiveAlert();
    setInterval(checkLiveAlert, CHECK_EVERY_MS);
  });
})();