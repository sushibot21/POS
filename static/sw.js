// Minimal service worker — exists so the PWA can be "installed" from Chrome.
// Strategy: network-first for everything. We do NOT precache HTML/JS, so a
// fresh deploy is picked up automatically on the next page load.
const CACHE = 'pos-static-v1';
const STATIC_ASSETS = ['/static/app-icon.png', '/static/manifest.webmanifest'];

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(STATIC_ASSETS)));
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  // Never intercept Socket.IO transport
  const url = new URL(req.url);
  if (url.pathname.startsWith('/socket.io/')) return;
  // Network-first; fall back to cache only if offline
  event.respondWith(
    fetch(req)
      .then((res) => {
        if (STATIC_ASSETS.includes(url.pathname)) {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(req, copy));
        }
        return res;
      })
      .catch(() => caches.match(req))
  );
});
