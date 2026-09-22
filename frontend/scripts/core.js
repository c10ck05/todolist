// PWA 서비스워커 등록 (http/https에서만 동작, file://에서는 무시)
if ('serviceWorker' in navigator && location.protocol.startsWith('http')) {
    window.addEventListener('load', () => navigator.serviceWorker.register('./sw.js').catch(() => {}));
}

const API_BASE = "https://todolist-ezpr.onrender.com";
let currentFilter = 'active';
let currentCategory = 'all';
let todos = [];
let viewMode = 'list'; // 'list' | 'timeline' | 'calendar'
let calendarDate = new Date();
let selectedCalKey = null;
const openPanels = new Set(); // 열려있는 상세 패널 id (재렌더 후에도 유지)
const REPEAT_LABELS = { none: '', daily: '매일', weekly: '매주', monthly: '매월', interval: '일 간격' };

// =====================
// 다크모드
// =====================
function toggleTheme() {
    const html = document.documentElement;
    const isDark = html.getAttribute('data-theme') === 'dark';
    html.setAttribute('data-theme', isDark ? 'light' : 'dark');
    document.getElementById('theme-btn').textContent = isDark ? '다크' : '라이트';
    localStorage.setItem('theme', isDark ? 'light' : 'dark');
}
(function () {
    const saved = localStorage.getItem('theme') || 'light';
    document.documentElement.setAttribute('data-theme', saved);
    document.addEventListener('DOMContentLoaded', () => {
        document.getElementById('theme-btn').textContent = saved === 'dark' ? '라이트' : '다크';
    });
})();

function togglePw(id, btn) {
    const el = document.getElementById(id);
    el.type = el.type === 'password' ? 'text' : 'password';
    btn.textContent = el.type === 'password' ? '표시' : '숨기기';
}
function showSection(id) {
    document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
    document.getElementById(id).classList.add('active');
}
function showAlert(id, msg, type = 'error') {
    const el = document.getElementById(id);
    el.className = `alert alert-${type}`;
    el.textContent = typeof msg === 'string' ? msg : '입력 내용을 확인한 뒤 다시 시도해주세요.';
    el.style.display = 'block';
    setTimeout(() => el.style.display = 'none', 4000);
}
function setLoading(btnId, loading, text) {
    const btn = document.getElementById(btnId);
    btn.disabled = loading;
    btn.innerHTML = loading ? `<span class="spinner"></span> 처리중...` : text;
}

function validatePassword(value, alertId, isNew = false) {
    let message = '';
    if (isNew && ([...value].length < 8 || !value.trim())) {
        message = '새 비밀번호는 공백만 사용할 수 없으며 8자 이상이어야 합니다.';
    } else if (new TextEncoder().encode(value).length > 72) {
        message = '비밀번호는 최대 72바이트까지 입력할 수 있어요. 한글은 보통 1자당 3바이트예요.';
    }
    if (message) showAlert(alertId, message);
    return !message;
}

function validateEmail(email, alertId) {
    const valid = email.length <= 100 && /^[^\s@]+@[^\s@.]+(?:\.[^\s@.]+)+$/.test(email);
    if (!valid) showAlert(alertId, '올바른 이메일 주소를 입력해주세요.');
    return valid;
}

function validateCode(code, alertId) {
    const valid = /^[0-9]{6}$/.test(code);
    if (!valid) showAlert(alertId, '인증번호는 숫자 6자리로 입력해주세요.');
    return valid;
}

function validateTodoInput(data) {
    for (const [key, limit, label] of [['content', 10000, '내용'], ['category', 50, '카테고리'], ['detail', 50000, '메모']]) {
        if (typeof data[key] === 'string' && [...data[key]].length > limit) {
            showAlert('todo-alert', `${label}은 ${limit.toLocaleString()}자 이하로 입력해주세요.`);
            return false;
        }
    }
    return true;
}

let sessionEpoch = 0;
let listRequestVersion = 0;
function captureSession() { return { token: localStorage.getItem('token'), epoch: sessionEpoch }; }
function isCurrentSession(session) {
    return session.epoch === sessionEpoch && session.token === localStorage.getItem('token');
}
function reportRequestError(session, error, alertId = 'todo-alert') {
    if (isCurrentSession(session)) showAlert(alertId, error.message || '연결을 확인하고 다시 시도해주세요.');
}
async function requestJson(session, path, options = {}) {
    if (!isCurrentSession(session)) throw new Error('이전 로그인 요청입니다.');
    const mutating = options.method && options.method !== 'GET';
    if (mutating) listRequestVersion++;
    const res = await fetch(API_BASE + path, {
        ...options,
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${session.token}`, ...options.headers }
    });
    if (!isCurrentSession(session)) throw new Error('이전 로그인 응답입니다.');
    if (res.status === 401) {
        logout();
        showAlert('login-alert', '로그인이 만료되었습니다. 다시 로그인해주세요.');
        throw new Error('로그인이 만료되었습니다.');
    }
    const data = await res.json();
    if (!isCurrentSession(session)) throw new Error('이전 로그인 응답입니다.');
    if (mutating) listRequestVersion++;
    if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '요청을 처리하지 못했어요.');
    return data;
}

document.addEventListener('DOMContentLoaded', () => {
    ['login-username', 'login-password'].forEach(id =>
        document.getElementById(id)?.addEventListener('keydown', e => e.key === 'Enter' && login())
    );
    ['signup-username', 'signup-password', 'signup-code'].forEach(id =>
        document.getElementById(id)?.addEventListener('keydown', e => e.key === 'Enter' && signup())
    );
    document.getElementById('signup-email')?.addEventListener('keydown', e => e.key === 'Enter' && requestSignupCode());
    ['reset-code', 'reset-new-password'].forEach(id =>
        document.getElementById(id)?.addEventListener('keydown', e => e.key === 'Enter' && resetPassword())
    );
    document.getElementById('reset-email')?.addEventListener('keydown', e => e.key === 'Enter' && requestResetCode());
    document.getElementById('todo-input')?.addEventListener('keydown', e => e.key === 'Enter' && addTodo());
});
