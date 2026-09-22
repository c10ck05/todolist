// Check the split HTML entrypoint and offline asset behavior without network access.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const root = path.join(__dirname, '..');
const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
const scripts = [...html.matchAll(/<script defer src="(\.\/[^\"]+)"><\/script>/g)].map(match => match[1]);
const styles = [...html.matchAll(/<link rel="stylesheet" href="(\.\/[^\"]+)">/g)].map(match => match[1]);
assert.equal(scripts.length, 5);
assert.equal(styles.length, 2);
const loaded = [];
const element = () => ({ addEventListener() {}, textContent: '', style: {}, classList: { add() {}, remove() {} } });
const browser = vm.createContext({
    navigator: {}, location: { protocol: 'file:' }, window: { addEventListener() {} },
    localStorage: { getItem() { return null; } },
    document: { documentElement: { setAttribute() {} }, getElementById: element,
        addEventListener(name, callback) { if (name === 'DOMContentLoaded') loaded.push(callback); } },
});
for (const file of scripts) vm.runInContext(fs.readFileSync(path.join(root, file), 'utf8'), browser, { filename: file });
for (const callback of loaded) callback();
assert.equal(typeof browser.login, 'function');
assert.equal(typeof browser.render, 'function');
assert.equal(typeof browser.importData, 'function');
for (const file of styles) assert.ok(fs.statSync(path.join(root, file)).size > 0);

const handlers = {}, cached = [], deleted = [], puts = [];
const offlineError = { offline: true };
const worker = vm.createContext({
    URL, location: { origin: 'https://test.invalid' },
    self: { addEventListener(name, handler) { handlers[name] = handler; }, skipWaiting() {}, clients: { claim() {} } },
    caches: { open: async () => ({ addAll: async assets => cached.push(...assets), put: async (...args) => puts.push(args) }),
        keys: async () => ['todo-v1', 'todo-v2', 'unrelated-cache'], delete: async name => deleted.push(name),
        match: async request => request === './index.html' ? 'offline HTML' : undefined },
    Response: { error: () => offlineError },
    fetch: async () => { throw new Error('offline'); },
});
vm.runInContext(fs.readFileSync(path.join(root, 'sw.js'), 'utf8'), worker);
async function run() {
    let work;
    handlers.install({ waitUntil(promise) { work = promise; } }); await work;
    for (const file of [...scripts, ...styles]) assert.ok(cached.includes(file), `Not cached: ${file}`);
    handlers.activate({ waitUntil(promise) { work = promise; } }); await work;
    assert.deepEqual(deleted, ['todo-v1']);
    for (const [mode, expected] of [['navigate', 'offline HTML'], ['cors', offlineError]]) {
        handlers.fetch({ request: { url: 'https://test.invalid/missing', method: 'GET', mode }, respondWith(promise) { work = promise; } });
        assert.equal(await work, expected);
    }
    worker.fetch = async () => ({ ok: false, status: 404 });
    handlers.fetch({ request: { url: 'https://test.invalid/missing.js', method: 'GET' }, respondWith(promise) { work = promise; } });
    assert.equal((await work).status, 404);
    assert.equal(puts.length, 0);
    console.log('Split frontend loading and offline asset checks passed.');
}
run().catch(error => { console.error(error); process.exitCode = 1; });
