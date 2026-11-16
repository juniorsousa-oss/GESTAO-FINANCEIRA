/* AXORA PWA — sem fetch handler e sem CacheStorage para dados privados. */
self.addEventListener("install", () => { self.skipWaiting(); });
self.addEventListener("activate", (event) => { event.waitUntil(self.clients.claim()); });
