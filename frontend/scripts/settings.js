function resetSessionView() {
    sessionEpoch++;
    listRequestVersion++;
    detailDrafts.clear();
    openPanels.clear();
    todoSaveQueues.clear();
    bulkInProgress = false;
    todos = [];
    currentFilter = 'active';
    currentCategory = 'all';
    viewMode = 'list';
    selectedCalKey = null;
    document.querySelectorAll('.tab-btn').forEach(button => button.classList.remove('active'));
    document.getElementById('tab-active').classList.add('active');
    applyViewVisibility();
    ['todo-list', 'timeline-view', 'calendar-view', 'category-filters', 'category-list', 'stats-bar'].forEach(id => {
        document.getElementById(id).innerHTML = '';
    });
    ['search-input', 'todo-input', 'todo-category', 'cur-pw', 'new-pw'].forEach(id => { document.getElementById(id).value = ''; });
    document.getElementById('todo-alert').style.display = 'none';
    document.getElementById('btn-add-todo').disabled = false;
    document.getElementById('btn-add-todo').innerHTML = '+ 등록';
    closeSettings();
}
function logout() {
    localStorage.removeItem('token');
    resetSessionView();
    showSection('section-login');
}
window.addEventListener('storage', event => {
    if (event.key !== 'token' && event.key !== null) return;
    resetSessionView();
    if (localStorage.getItem('token')) { showSection('section-todo'); loadTodos(); }
    else showSection('section-login');
});

// =====================
// 설정 / 데이터 / 계정
// =====================
function openSettings() {
    document.getElementById('settings-alert').style.display = 'none';
    document.getElementById('cur-pw').value = '';
    document.getElementById('new-pw').value = '';
    document.getElementById('settings-modal').classList.add('open');
}
function closeSettings() { document.getElementById('settings-modal').classList.remove('open'); }

// JSON 내보내기
function exportData() {
    const data = JSON.stringify(todos, null, 2);
    const blob = new Blob([data], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `todolist-backup-${dateKey(new Date())}.json`;
    a.click();
    URL.revokeObjectURL(url);
}

// JSON 가져오기 (서버에 새 항목으로 추가)
let importInProgress = false;
async function importData(fileInput) {
    if (importInProgress) return;
    const file = fileInput.files[0];
    if (!file) return;
    fileInput.value = '';
    if (file.size > 10 * 1024 * 1024) { showAlert('settings-alert', '백업 파일은 10MB 이하로 선택해주세요.'); return; }
    importInProgress = true;
    const session = captureSession();
    try {
        let items;
        try {
            items = JSON.parse(await file.text());
            if (!isCurrentSession(session)) return;
            if (!Array.isArray(items) || !items.length || items.length > 1000) throw new Error('형식 오류');
        } catch { showAlert('settings-alert', '1~1,000개 항목이 담긴 JSON 백업 파일을 선택해주세요.'); return; }
        if (!confirm(`${items.length}개 항목과 체크리스트·완료 상태를 가져올까요? (현재 목록에 추가됩니다)`)) return;
        await Promise.all([...todoSaveQueues.values()]);
        if (!isCurrentSession(session)) return;
        const result = await requestJson(session, '/todos/import', {
            method: 'POST',
            body: JSON.stringify({ items })
        });
        if (!isCurrentSession(session)) return;
        showAlert('settings-alert', `${result.imported}개 항목과 체크리스트를 복원했습니다.`, 'success');
        await loadTodos();
    } catch (e) {
        reportRequestError(session, new Error(`${e.message || '복원 결과를 확인하지 못했어요.'} 다시 가져오기 전에 목록을 새로고침해 확인해주세요.`), 'settings-alert');
    } finally { importInProgress = false; }
}

async function changePassword() {
    const cur = document.getElementById('cur-pw').value;
    const nw = document.getElementById('new-pw').value;
    if (!cur || !nw) { showAlert('settings-alert', '비밀번호를 모두 입력해주세요.'); return; }
    if (!validatePassword(cur, 'settings-alert') || !validatePassword(nw, 'settings-alert', true)) return;
    const session = captureSession();
    try {
        await requestJson(session, '/change-password', {
            method: 'POST',
            body: JSON.stringify({ current_password: cur, new_password: nw })
        });
        if (!isCurrentSession(session)) return;
        showAlert('settings-alert', '비밀번호가 변경되었습니다.', 'success');
        document.getElementById('cur-pw').value = '';
        document.getElementById('new-pw').value = '';
        closeSettings();
        logout();
        showAlert('login-alert', '비밀번호가 변경되었습니다. 다시 로그인해주세요.', 'success');
    } catch (error) { reportRequestError(session, error, 'settings-alert'); }
}

async function deleteAccount() {
    const pw = prompt('계정을 삭제하려면 비밀번호를 입력하세요.\n(모든 할 일이 영구 삭제됩니다)');
    if (!pw) return;
    if (!validatePassword(pw, 'settings-alert')) return;
    const session = captureSession();
    try {
        await requestJson(session, '/account', {
            method: 'DELETE',
            body: JSON.stringify({ password: pw })
        });
        if (!isCurrentSession(session)) return;
        alert('계정이 삭제되었습니다.');
        closeSettings();
        logout();
    } catch (error) { reportRequestError(session, error, 'settings-alert'); }
}

window.onload = () => {
    const token = localStorage.getItem('token');
    if (token) { showSection('section-todo'); loadTodos(); }
};
