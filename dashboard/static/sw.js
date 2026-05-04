// dashboard/static/sw.js — Service Worker minimal pour PWA
// Permet à iOS / Android de reconnaître l'app comme installable.
// V1 : pas de cache offline (pour éviter les soucis de version périmée).

self.addEventListener("install", (e) => self.skipWaiting());
self.addEventListener("activate", (e) => self.clients.claim());

self.addEventListener("fetch", (event) => {
    // Pass-through : toujours aller chercher la version live
    event.respondWith(fetch(event.request).catch(() => caches.match(event.request)));
});
