// Run with: node tests/frontend_validation.cjs (no network or browser required).
const vm = require('node:vm');
const assert = require('node:assert/strict');
const script = require('./frontend_source.cjs');
const elements = new Map();
function element(id) {
    if (!elements.has(id)) elements.set(id, { value: '', style: {}, classList: { add() {}, remove() {} } });
    return elements.get(id);
}
let requests = [];
const context = vm.createContext({
    TextEncoder, console, setTimeout() {}, setInterval() {},
    navigator: {}, location: { protocol: 'file:' }, window: { addEventListener() {} },
    localStorage: { getItem() { return null; }, setItem() {} },
    document: {
        getElementById: element, addEventListener() {}, querySelectorAll() { return []; },
        documentElement: { setAttribute() {} },
    },
    fetch: async (url, options) => {
        requests.push({ url, body: JSON.parse(options.body) });
        return { ok: false, status: 422, json: async () => ({ detail: '입력을 확인해주세요.' }) };
    },
});
vm.runInContext(script, context);
async function run() {
    for (const value of ['', '1234567', '        ', '가'.repeat(25), 'a'.repeat(73)]) {
        assert.equal(context.validatePassword(value, 'signup-alert', true), false);
    }
    assert.equal(context.validatePassword('가'.repeat(24), 'signup-alert', true), true);
    assert.equal(context.validatePassword('😀'.repeat(7), 'signup-alert', true), false);
    assert.equal(context.validatePassword('😀'.repeat(8), 'signup-alert', true), true);
    assert.equal(context.validatePassword('1234', 'login-alert'), true);
    assert.equal(context.validateCode('123456', 'signup-alert'), true);
    assert.equal(context.validateCode('12a456', 'signup-alert'), false);
    assert.equal(context.validateEmail('test@example.com', 'signup-alert'), true);
    assert.equal(context.validateEmail('bad@', 'signup-alert'), false);
    for (const [prefix, fn] of [['signup', 'signup'], ['reset', 'resetPassword']]) {
        element(`${prefix}-email`).value = 'test@example.com';
        element(`${prefix}-code`).value = '123456';
        element('signup-username').value = 'test';
        const passwordId = prefix === 'signup' ? 'signup-password' : 'reset-new-password';
        element(passwordId).value = 'short';
        requests = [];
        await context[fn]();
        assert.equal(requests.length, 0);
        element(passwordId).value = ' password123 ';
        await context[fn]();
        assert.equal(requests[0].body[prefix === 'signup' ? 'password' : 'new_password'], ' password123 ');
    }
    element('cur-pw').value = '1234';
    element('new-pw').value = 'short';
    requests = [];
    await context.changePassword();
    assert.equal(requests.length, 0);
    element('login-username').value = 'test';
    element('login-password').value = ' 1234 ';
    await context.login();
    assert.equal(requests[0].body.password, ' 1234 ');
    element('todo-input').value = 'keep this';
    element('todo-category').value = '';
    await context.addTodo();
    assert.equal(element('todo-input').value, 'keep this');
    assert.equal(vm.runInContext('todos.length', context), 0);
    assert.equal(element('todo-alert').textContent, '입력을 확인해주세요.');
    assert.equal(context.validateTodoInput({ category: 'a'.repeat(51) }), false);
    assert.equal(context.validateTodoInput({ category: '가'.repeat(50) }), true);
    // Same-item saves must be sent in order, preserving the newest draft.
    vm.runInContext('render = () => {}; loadTodos = async () => {}; todos = [{id: 1, detail: "initial", completed: true, subtasks: [{id: 9}]}]', context);
    const pending = [];
    requests = [];
    context.fetch = (url, options) => {
        requests.push(JSON.parse(options.body));
        return new Promise(resolve => pending.push(resolve));
    };
    vm.runInContext('detailDrafts.set("detail-input-1", "first")', context);
    const first = context.updateTodoField(1, { detail: 'first' });
    vm.runInContext('detailDrafts.set("detail-input-1", "second")', context);
    const second = context.updateTodoField(1, { detail: 'second' });
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(requests.length, 1);
    pending[0]({ ok: true, json: async () => ({ id: 1, detail: 'first', completed: false, subtasks: [] }) });
    await first;
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(requests.length, 2);
    assert.equal(vm.runInContext('detailDrafts.get("detail-input-1")', context), 'second');
    pending[1]({ ok: true, json: async () => ({ id: 1, detail: 'second', completed: false, subtasks: [] }) });
    await second;
    assert.equal(vm.runInContext('todos[0].detail', context), 'second');
    assert.equal(vm.runInContext('todos[0].completed', context), true);
    assert.equal(vm.runInContext('todos[0].subtasks.length', context), 1);
    assert.equal(vm.runInContext('detailDrafts.size', context), 0);
    assert.equal(vm.runInContext('todoSaveQueues.size', context), 0);
    // A failed save does not block the next save or discard its draft.
    context.fetch = async () => ({ ok: false, status: 400, json: async () => ({ detail: 'failed' }) });
    await context.updateTodoField(1, { detail: 'failed' });
    context.fetch = async () => ({ ok: true, json: async () => ({ detail: 'recovered' }) });
    await context.updateTodoField(1, { detail: 'recovered' });
    assert.equal(vm.runInContext('todos[0].detail', context), 'recovered');
    // Backups use one atomic request, retaining all exported state.
    const backup = [{ id: 1, content: 'backup', completed: true, sort_order: 3,
        subtasks: [{ id: 2, content: 'child', completed: true }] }];
    context.confirm = () => true;
    requests = [];
    context.fetch = async (url, options) => {
        requests.push({ url, body: JSON.parse(options.body) });
        return { ok: true, json: async () => ({ imported: 1 }) };
    };
    await context.importData({ value: 'backup.json', files: [{ text: async () => JSON.stringify(backup) }] });
    assert.equal(requests.length, 1);
    assert.ok(requests[0].url.endsWith('/todos/import'));
    assert.deepEqual(requests[0].body.items, backup);
    assert.equal(element('settings-alert').className, 'alert alert-success');
    context.fetch = async () => ({ ok: false, json: async () => ({ detail: 'Invalid backup' }) });
    await context.importData({ value: 'backup.json', files: [{ text: async () => JSON.stringify(backup) }] });
    assert.equal(element('settings-alert').className, 'alert alert-error');
    assert.ok(element('settings-alert').textContent.startsWith('Invalid backup'));
    console.log('Frontend validation and failed-save regression checks passed.');
}
run().catch(error => { console.error(error); process.exitCode = 1; });
