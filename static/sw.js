// News/Bench Service Worker
const CACHE_NAME = 'newsbench-v2';
const API_HOST = 'news-bench.onrender.com';
const STATIC_ASSETS = [
  'index.html',
  'style.css',
  'manifest.json',
  'offline.html'
];

// Install: cache static assets
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(STATIC_ASSETS))
      .then(() => self.skipWaiting())
  );
});

// Activate: clean old caches
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys.filter(key => key !== CACHE_NAME)
            .map(key => caches.delete(key))
      )
    ).then(() => self.clients.claim())
  );
});

// Fetch: network-first for API, cache-first for static
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);

  // API requests (cross-origin to Render): network only
  if (url.hostname === API_HOST || url.pathname.includes('/api/')) {
    event.respondWith(
      fetch(event.request)
        .catch(() => new Response(JSON.stringify({ error: 'Offline' }), {
          headers: { 'Content-Type': 'application/json' }
        }))
    );
    return;
  }

  // Local static assets: cache-first
  if (url.origin === self.location.origin) {
    event.respondWith(
      caches.match(event.request)
        .then(cached => cached || fetch(event.request).then(response => {
          const clone = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
          return response;
        }))
        .catch(() => caches.match('offline.html'))
    );
    return;
  }

  // Everything else: network with fallback
  event.respondWith(
    fetch(event.request)
      .catch(() => caches.match(event.request))
  );
});
