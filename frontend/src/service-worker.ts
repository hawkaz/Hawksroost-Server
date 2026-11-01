/// <reference lib="webworker" />
// Offline app shell + Web Push. API, video and radio always go to the network.
import { version } from '$app/environment';
import { assets, immutable } from '$app/manifest';

const sw = self as unknown as ServiceWorkerGlobalScope;
const CACHE = `shell-${version}`;
const SHELL = [...immutable.map((f) => f.path), ...assets.map((f) => f.path as string), '/200.html'];

sw.addEventListener('install', (event) => {
	event.waitUntil(
		caches
			.open(CACHE)
			.then((c) => c.addAll(SHELL))
			.then(() => sw.skipWaiting())
	);
});

sw.addEventListener('activate', (event) => {
	event.waitUntil(
		caches
			.keys()
			.then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
			.then(() => sw.clients.claim())
	);
});

sw.addEventListener('fetch', (event) => {
	const req = event.request;
	const url = new URL(req.url);
	if (req.method !== 'GET' || url.origin !== sw.location.origin) return;
	if (/^\/(api|video|radio)\//.test(url.pathname)) return;

	if (req.mode === 'navigate') {
		// Fresh page when online; cached shell when the cabin or this device is offline.
		event.respondWith(fetch(req).catch(async () => (await caches.match('/200.html')) ?? Response.error()));
		return;
	}
	event.respondWith(
		caches.match(req).then(
			(hit) =>
				hit ??
				fetch(req).then((res) => {
					if (res.ok && SHELL.includes(url.pathname)) {
						const copy = res.clone();
						caches.open(CACHE).then((c) => c.put(req, copy));
					}
					return res;
				})
		)
	);
});

sw.addEventListener('push', (event) => {
	let data: { title?: string; body?: string; url?: string; tag?: string; image?: string } = {};
	try {
		data = event.data?.json() ?? {};
	} catch {
		data = { title: 'Hawksroost', body: event.data?.text() };
	}
	event.waitUntil(
		sw.registration.showNotification(data.title || 'Hawksroost', {
			body: data.body,
			tag: data.tag || undefined,
			icon: '/icons/icon-192.png',
			badge: '/icons/favicon-32.png',
			data: { url: data.url || '/' },
			...(data.image ? { image: data.image } : {})
		} as NotificationOptions)
	);
});

sw.addEventListener('notificationclick', (event) => {
	event.notification.close();
	const target = new URL(event.notification.data?.url || '/', sw.location.origin).href;
	event.waitUntil(
		sw.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((wins) => {
			for (const w of wins) {
				if ('focus' in w) {
					(w as WindowClient).navigate(target);
					return (w as WindowClient).focus();
				}
			}
			return sw.clients.openWindow(target);
		})
	);
});
