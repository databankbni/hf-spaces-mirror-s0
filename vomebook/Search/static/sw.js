const CACHE_NAME = "vomebook-search-v1.0.0";

const PRECACHE_URLS = [
  "/",
  "/static/style.css",
  "/static/app.js",
  "/manifest.json",
  "/data/initial/manifest.json",
  "/data/sidebar/manifest.json"
];

function cacheManifestUrls(cache, manifestUrl) {
  return fetch(manifestUrl)
    .then((response) => response.ok ? response.json() : null)
    .then((manifest) => {
      const urls = manifest && Array.isArray(manifest.urls) ? manifest.urls : [];
      return urls.length ? cache.addAll(urls) : null;
    });
}

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(PRECACHE_URLS).then(() => {
        return Promise.all([
          cacheManifestUrls(cache, "/data/initial/manifest.json"),
          cacheManifestUrls(cache, "/data/sidebar/manifest.json")
        ]);
      }).catch((err) => {
        console.warn("[SW] precache partial failure:", err);
      });
    }).then(() => self.skipWaiting())
  );
});
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))
      );
    }).then(() => self.clients.claim())
  );
});
self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (url.hostname !== self.location.hostname || event.request.method !== "GET") {
    return;
  }
  const cacheable = url.pathname.startsWith("/static/")
    || url.pathname.startsWith("/icons/")
    || url.pathname.startsWith("/data/initial/")
    || url.pathname.startsWith("/data/sidebar/")
    || url.pathname === "/manifest.json";
  if (!cacheable) {
    return;
  }
  event.respondWith(
    caches.match(event.request).then((cached) => {
      const fetchPromise = fetch(event.request).then((response) => {
        if (response.ok && response.status !== 206) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(event.request, clone);
          });
        }
        return response;
      }).catch(() => cached);
      return cached || fetchPromise;
    })
  );
});
