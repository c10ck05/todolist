// Deterministic delayed-response tests. No production network requests.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync(require('node:path').join(__dirname, '../index.html'), 'utf8')
    .match(/<script>([\s\S]*?)<\/script>/)[1];
const tick = () => new Promise(resolve => setImmediate(resolve));
const response = (data, status = 200) => ({ ok: status < 400, status, json: async () => data });
function fixture() {
    let token = 'A';
    const elements = new Map(), pending = [], events = {};
    const el = id => {
        if (!elements.has(id)) elements.set(id, {
            value: '', innerHTML: '', style: {}, classList: { add() {}, remove() {}, toggle() {} },
        });
        return elements.get(id);
    };
    const context = vm.createContext({
        TextEncoder, console: { log() {}, error() {} }, setTimeout() {},
        navigator: {}, location: { protocol: 'file:' }, confirm: () => true, alert() {},
        window: { addEventListener(name, handler) { events[name] = handler; } },
        localStorage: { getItem: () => token, setItem: (key, value) => { token = value; }, removeItem: () => { token = null; } },
        document: { getElementById: el, querySelector: el, querySelectorAll: () => [],
            addEventListener() {}, documentElement: { setAttribute() {} } },
        fetch: (url, options) => new Promise((resolve, reject) => pending.push({ url, options, resolve, reject })),
    });
    vm.runInContext(source, context);
    vm.runInContext('render = () => {}', context);
    return { context, el, pending, events, token: () => token, setToken: value => { token = value; },
        run: code => vm.runInContext(code, context), todos: () => JSON.parse(vm.runInContext('JSON.stringify(todos)', context)) };
}
async function run() {
    // A response after switching accounts cannot display old data or log B out.
    for (const status of [200, 401]) {
        const f = fixture();
        const old = f.context.loadTodos();
        f.context.logout(); f.setToken('B');
        const fresh = f.context.loadTodos();
        f.pending[1].resolve(response([{ id: 2, content: 'B private' }])); await fresh;
        f.pending[0].resolve(response([{ id: 1, content: 'A private' }], status)); await old;
        assert.equal(f.token(), 'B');
        assert.equal(f.todos()[0].content, 'B private');
    }
    // Parsing JSON can itself be delayed across a session switch.
    {
        const f = fixture(); let finishJson;
        const old = f.context.loadTodos();
        f.pending[0].resolve({ ok: true, status: 200, json: () => new Promise(resolve => { finishJson = resolve; }) });
        await tick(); f.context.logout(); f.setToken('B');
        finishJson([{ content: 'A private' }]); await old;
        assert.deepEqual(f.todos(), []);
    }
    // Same-session load ordering and error responses must not corrupt the list.
    {
        const f = fixture(); const old = f.context.loadTodos(), latest = f.context.loadTodos();
        f.pending[1].resolve(response([{ id: 2 }])); await latest;
        f.pending[0].resolve(response([{ id: 1 }])); await old;
        assert.equal(f.todos()[0].id, 2);
        const failed = f.context.loadTodos();
        f.pending[2].resolve(response({ detail: 'unavailable' }, 500)); await failed;
        assert.equal(f.todos()[0].id, 2);
    }
    // Save then remove must reach the server in this order, not race.
    {
        const f = fixture(); f.run('todos = [{id: 1, deadline: null}]');
        f.el('deadline-input-1').value = '2026-10-01T12:00';
        const save = f.context.saveDeadline(1), remove = f.context.removeDeadline(1);
        await tick(); assert.equal(f.pending.length, 1);
        f.pending[0].resolve(response({ deadline: '2026-10-01T12:00:00' })); await save; await tick();
        assert.equal(f.pending.length, 2);
        assert.equal(JSON.parse(f.pending[1].options.body).deadline, null);
        f.pending[1].resolve(response({ deadline: null })); await remove;
        assert.equal(f.todos()[0].deadline, null);
    }
    // Queued requests are cancelled after logout, even if the token is reused.
    {
        const f = fixture(); f.run('todos = [{id: 1}]');
        const first = f.context.updateTodoField(1, { detail: 'one' });
        const second = f.context.updateTodoField(1, { detail: 'two' });
        await tick(); f.context.logout(); f.setToken('A');
        f.pending[0].resolve(response({ detail: 'one' })); await Promise.all([first, second]);
        assert.equal(f.pending.length, 1); assert.deepEqual(f.todos(), []);
    }
    // Failed deletes stay visible; repeated bulk clicks do not issue extra requests.
    {
        const f = fixture(); f.run('todos = [{id: 1, completed: true}, {id: 2, completed: true}]');
        const bulk = f.context.clearCompleted(); await tick();
        await f.context.clearCompleted(); assert.equal(f.pending.length, 1);
        f.pending[0].resolve(response({ detail: 'failed' }, 500)); await tick();
        f.pending[1].resolve(response({ message: 'deleted' })); await bulk;
        assert.deepEqual(f.todos().map(t => t.id), [1]);
        assert.match(f.el('todo-alert').textContent, /1개/);
    }
    {
        const f = fixture(); f.run('todos = [{id: 1, completed: false}]');
        const bulk = f.context.completeAll(); await tick(); await f.context.completeAll();
        f.pending[0].resolve(response({ id: 1, completed: true })); await bulk;
        assert.equal(f.pending.length, 1); assert.equal(f.todos()[0].completed, true);
    }
    // Imported file must not be sent to a different account after async file reading.
    {
        const f = fixture(); let finishRead;
        const importing = f.context.importData({ value: 'backup.json', files: [{ text: () => new Promise(resolve => { finishRead = resolve; }) }] });
        f.context.logout(); f.setToken('B'); finishRead('[{"content":"A private"}]'); await importing;
        assert.equal(f.pending.length, 0);
    }
    // Old creation results cannot append data or clear the new account's draft.
    {
        const f = fixture(); f.el('todo-input').value = 'A private';
        const adding = f.context.addTodo(); f.context.logout(); f.setToken('B');
        f.el('todo-input').value = 'B draft';
        f.pending[0].resolve(response({ id: 1, content: 'A private' })); await adding;
        assert.deepEqual(f.todos(), []); assert.equal(f.el('todo-input').value, 'B draft');
    }
    // Another tab's logout clears already-rendered private content and invalidates requests.
    {
        const f = fixture(); f.el('todo-list').innerHTML = 'A private';
        const loading = f.context.loadTodos();
        f.setToken(null); f.events.storage({ key: 'token' });
        assert.equal(f.el('todo-list').innerHTML, '');
        f.pending[0].resolve(response([{ content: 'A private' }])); await loading;
        assert.deepEqual(f.todos(), []);
    }
    // An old list snapshot must not undo a successful mutation.
    {
        const f = fixture(); f.run('todos = [{id: 1, detail: "old"}]');
        const loading = f.context.loadTodos();
        const saving = f.context.updateTodoField(1, { detail: 'new' }); await tick();
        f.pending[1].resolve(response({ detail: 'new' })); await saving;
        f.pending[0].resolve(response([{ id: 1, detail: 'old' }])); await loading;
        assert.equal(f.todos()[0].detail, 'new');
    }
    console.log('Frontend session isolation, request ordering and bulk-failure checks passed.');
}
run().catch(error => { console.error(error); process.exitCode = 1; });
