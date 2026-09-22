// =====================
// 로그인 / 회원가입 / 재설정
// =====================
async function login() {
    if (document.getElementById('btn-login').disabled) return;
    const username = document.getElementById('login-username').value.trim();
    const password = document.getElementById('login-password').value;
    if (!username || !password) { showAlert('login-alert', '아이디와 비밀번호를 입력해주세요.'); return; }
    if (!validatePassword(password, 'login-alert')) return;
    const session = captureSession();
    setLoading('btn-login', true, '로그인');
    try {
        const res = await fetch(`${API_BASE}/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
        });
        const data = await res.json();
        if (!isCurrentSession(session)) return;
        if (!res.ok) { showAlert('login-alert', data.detail || '로그인 실패'); return; }
        localStorage.setItem('token', data.access_token);
        resetSessionView();
        showSection('section-todo');
        loadTodos();
    } catch (error) { reportRequestError(session, error, 'login-alert'); }
    finally { setLoading('btn-login', false, '로그인'); }
}

async function requestSignupCode() {
    const email = document.getElementById('signup-email').value.trim();
    if (!validateEmail(email, 'signup-alert')) return;
    const btn = document.getElementById('btn-request-code');
    btn.disabled = true; btn.textContent = '발송중...';
    try {
        const res = await fetch(`${API_BASE}/request-code`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email })
        });
        const data = await res.json();
        if (!res.ok) { showAlert('signup-alert', data.detail || '요청 실패'); btn.disabled = false; btn.textContent = '인증 요청'; return; }
        showAlert('signup-success', '인증번호가 발송되었습니다!', 'success');
        startCooldown(btn, 180);
    } catch { showAlert('signup-alert', '서버 오류'); btn.disabled = false; btn.textContent = '인증 요청'; }
}

async function signup() {
    const username = document.getElementById('signup-username').value.trim();
    const password = document.getElementById('signup-password').value;
    const email = document.getElementById('signup-email').value.trim();
    const code = document.getElementById('signup-code').value.trim();
    if (!username || !password || !email || !code) { showAlert('signup-alert', '모든 항목을 입력해주세요.'); return; }
    if ([...username].length > 50) { showAlert('signup-alert', '아이디는 50자 이하로 입력해주세요.'); return; }
    if (!validatePassword(password, 'signup-alert', true) || !validateEmail(email, 'signup-alert') || !validateCode(code, 'signup-alert')) return;
    setLoading('btn-signup', true, '인증 및 가입 완료');
    try {
        const res = await fetch(`${API_BASE}/signup`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password, email, code })
        });
        const data = await res.json();
        if (!res.ok) { showAlert('signup-alert', data.detail || '회원가입 실패'); return; }
        showAlert('signup-success', '회원가입 성공! 로그인 해주세요.', 'success');
        setTimeout(() => showSection('section-login'), 1500);
    } catch { showAlert('signup-alert', '서버 오류가 발생했습니다.'); }
    finally { setLoading('btn-signup', false, '인증 및 가입 완료'); }
}

async function requestResetCode() {
    const email = document.getElementById('reset-email').value.trim();
    if (!validateEmail(email, 'reset-alert')) return;
    const btn = document.getElementById('btn-request-reset-code');
    btn.disabled = true; btn.textContent = '발송중...';
    try {
        const res = await fetch(`${API_BASE}/request-reset-code`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email })
        });
        const data = await res.json();
        if (!res.ok) { showAlert('reset-alert', data.detail || '요청 실패'); btn.disabled = false; btn.textContent = '인증 요청'; return; }
        showAlert('reset-success', '인증번호가 발송되었습니다!', 'success');
        startCooldown(btn, 180);
    } catch { showAlert('reset-alert', '서버 오류'); btn.disabled = false; btn.textContent = '인증 요청'; }
}

async function resetPassword() {
    const email = document.getElementById('reset-email').value.trim();
    const code = document.getElementById('reset-code').value.trim();
    const new_password = document.getElementById('reset-new-password').value;
    if (!email || !code || !new_password) { showAlert('reset-alert', '모든 항목을 입력해주세요.'); return; }
    if (!validatePassword(new_password, 'reset-alert', true) || !validateEmail(email, 'reset-alert') || !validateCode(code, 'reset-alert')) return;
    setLoading('btn-reset', true, '비밀번호 변경');
    try {
        const res = await fetch(`${API_BASE}/reset-password`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, code, new_password })
        });
        const data = await res.json();
        if (!res.ok) { showAlert('reset-alert', data.detail || '재설정 실패'); return; }
        showAlert('reset-success', '비밀번호가 변경되었습니다!', 'success');
        setTimeout(() => showSection('section-login'), 1500);
    } catch { showAlert('reset-alert', '서버 오류가 발생했습니다.'); }
    finally { setLoading('btn-reset', false, '비밀번호 변경'); }
}

function startCooldown(btn, seconds) {
    let count = seconds;
    const timer = setInterval(() => {
        btn.textContent = `재요청 (${count}s)`;
        count--;
        if (count < 0) { clearInterval(timer); btn.disabled = false; btn.textContent = '인증 요청'; }
    }, 1000);
}
