// VenueFlow Service Worker — Offline-capable PWA
// Caches static assets + last known zone data so the app works
// even when stadium WiFi drops during peak load.

const CACHE_NAME = 'venueflow-v1';
const ZONE_CACHE = 'venueflow-zones-v1';

// Static assets to cache on install
const STATIC_ASSETS = [
  '/',
  '/index.html',
  '/styles.css',
  '/app.js',
];

// ── Install: cache static shell ──────────────────────────────────────────────
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_ASSETS);
    })
  );
  self.skipWaiting();
});

// ── Activate: clean old caches ───────────────────────────────────────────────
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((k) => k !== CACHE_NAME && k !== ZONE_CACHE)
          .map((k) => caches.delete(k))
      )
    )
  );
  self.clients.claim();
});

// ── Fetch: network-first for API, cache-first for static ────────────────────
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // API calls: network first, fall back to cached zone data
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(networkFirstWithZoneCache(event.request));
    return;
  }

  // WebSocket: never intercept
  if (url.protocol === 'ws:' || url.protocol === 'wss:') {
    return;
  }

  // Static assets: cache first, network fallback
  event.respondWith(
    caches.match(event.request).then((cached) => {
      return cached || fetch(event.request).then((response) => {
        if (response && response.status === 200) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
        }
        return response;
      });
    })
  );
});

async function networkFirstWithZoneCache(request) {
  const cache = await caches.open(ZONE_CACHE);
  try {
    const response = await fetch(request);
    // Cache successful zone/waittimes responses for offline fallback
    if (response.ok && (
      request.url.includes('/api/zones') ||
      request.url.includes('/api/waittimes') ||
      request.url.includes('/api/alerts')
    )) {
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    // Network failed — serve stale cache with a warning header
    const cached = await cache.match(request);
    if (cached) {
      const headers = new Headers(cached.headers);
      headers.set('X-Served-From', 'cache');
      headers.set('X-Cache-Warning', 'Offline mode — data may be up to 5 minutes old');
      return new Response(await cached.blob(), {
        status: cached.status,
        statusText: cached.statusText,
        headers,
      });
    }
    // Nothing in cache either — return a graceful empty response
    return new Response(JSON.stringify([]), {
      headers: { 'Content-Type': 'application/json', 'X-Served-From': 'empty-fallback' },
    });
  }
}

// ── Background sync: queue route requests when offline ──────────────────────
self.addEventListener('sync', (event) => {
  if (event.tag === 'sync-preferences') {
    event.waitUntil(syncPreferences());
  }
});

async function syncPreferences() {
  // When connectivity returns, sync any queued preference saves
  const db = await openDB();
  const pending = await getAll(db, 'pending-syncs');
  for (const item of pending) {
    try {
      await fetch('/api/session', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(item),
      });
    } catch {
      // Will retry on next sync event
    }
  }
}

// Minimal IndexedDB helpers for sync queue
function openDB() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open('venueflow-sync', 1);
    req.onupgradeneeded = () => req.result.createObjectStore('pending-syncs', { autoIncrement: true });
    req.onsuccess = () => resolve(req.result);
    req.onerror = reject;
  });
}

function getAll(db, storeName) {
  return new Promise((resolve) => {
    const tx = db.transaction(storeName, 'readonly');
    const req = tx.objectStore(storeName).getAll();
    req.onsuccess = () => resolve(req.result || []);
    req.onerror = () => resolve([]);
  });
}
