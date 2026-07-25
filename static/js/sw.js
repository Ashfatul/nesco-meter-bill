// NESCO Prepaid Tracker Service Worker
// Strategy: Network Only (No Caching, Online Mode Only)

const CACHE_NAME = 'nesco-tracker-v1';

// Install event - force activate immediately
self.addEventListener('install', event => {
  self.skipWaiting();
});

// Activate event - claim clients
self.addEventListener('activate', event => {
  event.waitUntil(self.clients.claim());
});

// Fetch event - direct network pass-through
self.addEventListener('fetch', event => {
  event.respondWith(fetch(event.request));
});
