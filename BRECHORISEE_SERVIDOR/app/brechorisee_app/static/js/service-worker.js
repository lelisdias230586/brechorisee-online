const CACHE_NAME = "brechorisee-mobile-v46-atendimento-bot-desejos-aquisicoes";
const ASSETS = [
  "/static/css/style.css",
  "/static/js/online-store.js",
  "/static/js/customer-live-notifications.js",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png",
  "/static/img/logo-brechorisee.png",
  "/static/img/logo-brechorisee-tight.png",
  "/static/manifest_cliente.webmanifest"
];

self.addEventListener("install", event => {
  event.waitUntil(caches.open(CACHE_NAME).then(cache => cache.addAll(ASSETS).catch(() => null)));
  self.skipWaiting();
});

self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys().then(keys => Promise.all(keys.filter(key => key !== CACHE_NAME).map(key => caches.delete(key))))
  );
  self.clients.claim();
});

self.addEventListener("fetch", event => {
  if (event.request.method !== "GET") return;
  const url = new URL(event.request.url);
  if (url.pathname.startsWith("/static/")) {
    event.respondWith(
      caches.match(event.request).then(cached => cached || fetch(event.request).then(response => {
        const copy = response.clone();
        caches.open(CACHE_NAME).then(cache => cache.put(event.request, copy));
        return response;
      }).catch(() => cached))
    );
  }
});


self.addEventListener("notificationclick", event => {
  event.notification.close();
  const data = event.notification.data || {};
  const url = data.url || "/cliente/live";
  event.waitUntil(
    clients.matchAll({ type: "window", includeUncontrolled: true }).then(clientList => {
      for (const client of clientList) {
        if ("focus" in client) {
          client.navigate(url);
          return client.focus();
        }
      }
      if (clients.openWindow) return clients.openWindow(url);
    })
  );
});
