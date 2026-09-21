// Run with: node tests/frontend_validation.cjs (no network or browser required).
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const html = fs.readFileSync(require('node:path').join(__dirname, '../index.html'), 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const elements = new Map();
function element(id) {
    if (!elements.has(id)) elements.set(id, { value: '', style: {}, classList: { add() {}, remove() {} } });
    return elements.get(id);
}
let requests = [];
const context = vm.createContext({
    TextEncoder, console, setTimeout() {}, setInterval() {},
    navigator: {}, location: { protocol: 'file:' }, window: {},
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
    console.log('Frontend validation and failed-save regression checks passed.');
}
run().catch(error => { console.error(error); process.exitCode = 1; });
