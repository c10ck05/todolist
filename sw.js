// 간단한 서비스워커: 앱 셸 캐시(네트워크 우선, 오프라인 시 캐시 폴백)
const CACHE = 'todo-v2';
const ASSETS = ['./', './index.html', './manifest.json', './icon.svg',
    './frontend/styles/base.css', './frontend/styles/theme.css',
    './frontend/scripts/core.js', './frontend/scripts/auth.js',
    './frontend/scripts/todos.js', './frontend/scripts/views.js', './frontend/scripts/settings.js'];

self.addEventListener('install', (e) => {
    e.waitUntil(caches.open(CACHE).then((c) => c.addAll(ASSETS)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
    e.waitUntil(
        caches.keys().then((keys) => Promise.all(keys.filter((k) => k.startsWith('todo-') && k !== CACHE).map((k) => caches.delete(k))))
            .then(() => self.clients.claim())
    );
});

self.addEventListener('fetch', (e) => {
    const url = new URL(e.request.url);
    // API(다른 오리진) 요청은 서비스워커가 개입하지 않음
    if (url.origin !== location.origin || e.request.method !== 'GET') return;
    e.respondWith(
        fetch(e.request)
            .then((res) => {
                if (!res.ok) return res;
                const copy = res.clone();
                caches.open(CACHE).then((c) => c.put(e.request, copy)).catch(() => {});
                return res;
            })
            .catch(() => caches.match(e.request).then((r) => r || (e.request.mode === 'navigate'
                ? caches.match('./index.html') : Response.error())))
    );
});
