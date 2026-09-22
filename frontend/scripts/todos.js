// =====================
// 투두 CRUD
// =====================
async function loadTodos() {
    const session = captureSession();
    const version = ++listRequestVersion;
    try {
        const loaded = await requestJson(session, '/todos');
        if (!isCurrentSession(session) || version !== listRequestVersion) return;
        if (!Array.isArray(loaded)) throw new Error('목록을 불러오지 못했어요. 다시 시도해주세요.');
        todos = loaded;
        render();
    } catch (error) { reportRequestError(session, error); }
}

async function addTodo() {
    const input = document.getElementById('todo-input');
    const catInput = document.getElementById('todo-category');
    const content = input.value.trim();
    const category = catInput.value.trim() || null;
    if (!content) { input.style.borderColor = '#cc1016'; setTimeout(() => input.style.borderColor = '', 1000); return; }
    if (!validateTodoInput({ content, category })) return;
    const btn = document.getElementById('btn-add-todo');
    if (btn.disabled) return;
    btn.disabled = true; btn.innerHTML = '<span class="spinner"></span>';
    const session = captureSession();
    try {
        const newTodo = await requestJson(session, '/todos', { method: 'POST', body: JSON.stringify({ content, category }) });
        if (!isCurrentSession(session)) return;
        todos.push(newTodo);
        if (input.value.trim() === content) input.value = '';
        if ((catInput.value.trim() || null) === category) catInput.value = '';
        render();
    } catch (error) { reportRequestError(session, error); }
    finally { if (isCurrentSession(session)) { btn.disabled = false; btn.innerHTML = '+ 등록'; } }
}

const todoSaveQueues = new Map();
function queueTodoSave(id, session, save) {
    const previous = todoSaveQueues.get(id) || Promise.resolve();
    const next = previous.catch(() => {}).then(() => {
        if (isCurrentSession(session)) return save();
    });
    todoSaveQueues.set(id, next);
    const cleanup = () => { if (todoSaveQueues.get(id) === next) todoSaveQueues.delete(id); };
    next.then(cleanup, cleanup);
    return next;
}

async function updateTodoField(id, patch) {
    if (!validateTodoInput(patch)) return;
    const fields = Object.keys(patch).flatMap(key => key === 'repeat'
        ? [`repeat-input-${id}`, `repeat-interval-${id}`, ...Object.keys(WEEKDAYS).map(day => `repeat-day-${id}-${day}`)]
        : [`${key}-input-${id}`]);
    const submitted = snapshotDrafts(fields);
    const session = captureSession();
    return queueTodoSave(id, session, async () => {
        try {
            const updated = await requestJson(session, `/todos/${id}`, { method: 'PATCH', body: JSON.stringify(patch) });
            if (!isCurrentSession(session)) return;
            const todo = todos.find(t => t.id === id);
            if (todo) Object.keys(patch).forEach(key => { todo[key] = updated[key]; });
            acknowledgeDrafts(submitted);
            render();
        } catch (error) { reportRequestError(session, error); }
    });
}
function updateCategory(id, value) { updateTodoField(id, { category: value.trim() || null }); }
function changeRepeatType(id, value) {
    document.getElementById(`repeat-interval-${id}`).hidden = value !== 'interval';
    document.getElementById(`repeat-custom-${id}`).hidden = value !== 'custom';
}
async function saveRepeat(id) {
    const type = document.getElementById(`repeat-input-${id}`).value;
    const days = Array.from(document.querySelectorAll(`#repeat-days-${id} input:checked`), el => el.value);
    if (type === 'custom' && !days.length) { alert('반복할 요일을 하나 이상 선택해주세요.'); return; }
    const repeat = type === 'custom' ? { type: 'weekly', days } : { type };
    if (type === 'interval') {
        repeat.value = Number(document.getElementById(`repeat-interval-${id}`).value);
        if (!Number.isInteger(repeat.value) || repeat.value < 1 || repeat.value > 3650) { alert('반복 간격은 1~3650일로 입력해주세요.'); return; }
    }
    await updateTodoField(id, { repeat });
}
function updatePriority(id, value) { updateTodoField(id, { priority: parseInt(value, 10) }); }
function updateDetail(id, value) { updateTodoField(id, { detail: value.trim() || null }); }

async function toggleTodo(id) {
    const session = captureSession();
    return queueTodoSave(id, session, async () => {
        try {
            await performToggle(id, session);
        } catch (error) { reportRequestError(session, error); }
    });
}
async function performToggle(id, session) {
    const updated = await requestJson(session, `/todos/${id}/toggle`, { method: 'PATCH' });
    if (!isCurrentSession(session)) return;
    const todo = todos.find(t => t.id === id);
    if (todo) todo.completed = updated.completed;
    if (updated.spawned && !todos.some(t => t.id === updated.spawned.id)) todos.push(updated.spawned);
    render();
}
async function performDelete(id, session) {
    await requestJson(session, `/todos/${id}`, { method: 'DELETE' });
    if (!isCurrentSession(session)) return;
    todos = todos.filter(t => t.id !== id);
    openPanels.delete(id);
    render();
}
async function deleteTodo(id) {
    const session = captureSession();
    return queueTodoSave(id, session, async () => {
        try { await performDelete(id, session); }
        catch (error) { reportRequestError(session, error); }
    });
}

// =====================
// 마감기한
// =====================
function fillDeadlineInput(id) {
    const todo = todos.find(t => t.id === id);
    const input = document.getElementById(`deadline-input-${id}`);
    if (todo?.deadline && input)
        input.value = todo.deadline.slice(0, 16);
}

function toggleDeadlinePanel(id) {
    if (openPanels.has(id)) openPanels.delete(id);
    else openPanels.add(id);
    applyOpenPanels();
}

// 재렌더 후에도 열려있던 패널 상태를 복원
function applyOpenPanels() {
    document.querySelectorAll('.deadline-panel').forEach(p => p.classList.remove('open'));
    document.querySelectorAll('.btn-deadline').forEach(b => { b.classList.remove('active'); b.setAttribute('aria-expanded', 'false'); });
    openPanels.forEach(id => {
        const panel = document.getElementById(`deadline-panel-${id}`);
        const btn = document.getElementById(`btn-deadline-${id}`);
        if (!panel) { openPanels.delete(id); return; }
        panel.classList.add('open');
        if (btn) { btn.classList.add('active'); btn.setAttribute('aria-expanded', 'true'); }
    });
}

async function saveDeadline(id) {
    const value = document.getElementById(`deadline-input-${id}`).value;
    if (!value) { alert('날짜와 시간을 선택해주세요.'); return; }
    return persistDeadline(id, value);
}
async function removeDeadline(id) { return persistDeadline(id, null); }
async function persistDeadline(id, value) {
    const submitted = snapshotDrafts([`deadline-input-${id}`]);
    const session = captureSession();
    return queueTodoSave(id, session, async () => {
        try {
            const updated = await requestJson(session, `/todos/${id}/deadline`, {
                method: 'PATCH', body: JSON.stringify({ deadline: value })
            });
            if (!isCurrentSession(session)) return;
            const todo = todos.find(t => t.id === id);
            if (todo) todo.deadline = updated.deadline;
            acknowledgeDrafts(submitted);
            render();
        } catch (error) { reportRequestError(session, error); }
    });
}

// =====================
// 필터 / 뷰 전환
// =====================
// 뷰(리스트/타임라인/캘린더)에 따라 화면 요소 표시 전환
function applyViewVisibility() {
    const isList = viewMode === 'list';
    document.getElementById('todo-list').style.display = isList ? '' : 'none';
    document.querySelector('.list-tools').style.display = isList ? 'flex' : 'none';
    document.getElementById('stats-bar').style.display = isList ? '' : 'none';
    document.getElementById('timeline-view').classList.toggle('active', viewMode === 'timeline');
    document.getElementById('calendar-view').classList.toggle('active', viewMode === 'calendar');
    document.getElementById('category-filters').style.display = isList ? '' : 'none';
}

function filterTodos(filter, btn) {
    viewMode = 'list';
    currentFilter = filter;
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    applyViewVisibility();
    render();
}

function switchToTimeline(btn) {
    viewMode = 'timeline';
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    applyViewVisibility();
    renderTimeline();
}

function switchToCalendar(btn) {
    viewMode = 'calendar';
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    applyViewVisibility();
    renderCalendar();
}

function isOverdue(todo) {
    if (!todo.deadline || todo.completed) return false;
    return new Date(todo.deadline) < new Date();
}

function formatDeadline(isoStr) {
    if (!isoStr) return '';
    const d = new Date(isoStr);
    const isOD = d < new Date();
    const month = d.getMonth() + 1;
    const day = d.getDate();
    const hour = d.getHours().toString().padStart(2, '0');
    const min = d.getMinutes().toString().padStart(2, '0');
    return `${isOD ? '마감 초과 · ' : ''}${month}/${day} ${hour}:${min}`;
}

// 우선순위 (0=낮음, 1=보통, 2=높음)
const PRIORITY_LABELS = { 0: '낮음', 1: '보통', 2: '높음' };
function priorityBadge(p) {
    if (p === 2) return `<span class="priority-badge p-high"> 높음</span>`;
    if (p === 0) return `<span class="priority-badge p-low"> 낮음</span>`;
    return '';
}
function priorityOptions(selected) {
    const sel = (selected == null) ? 1 : selected;
    return [[2, '높음'], [1, '보통'], [0, '낮음']].map(([v, l]) =>
        `<option value="${v}" ${v === sel ? 'selected' : ''}>${l}</option>`
    ).join('');
}

// D-day 뱃지
function ddayBadge(isoStr, completed) {
    if (!isoStr || completed) return '';
    const target = new Date(isoStr);
    const today = new Date(); today.setHours(0, 0, 0, 0);
    const day0 = new Date(target); day0.setHours(0, 0, 0, 0);
    const diff = Math.round((day0 - today) / 86400000);
    let label;
    if (diff === 0) label = 'D-DAY';
    else if (diff > 0) label = `D-${diff}`;
    else label = `D+${-diff}`;
    return `<span class="dday-badge ${diff <= 0 ? 'urgent' : ''}">${label}</span>`;
}

// 검색 + 정렬 적용
function applySort(arr) {
    const mode = document.getElementById('sort-select').value;
    const copy = [...arr];
    if (mode === 'deadline') {
        copy.sort((a, b) => {
            if (!a.deadline && !b.deadline) return a.id - b.id;
            if (!a.deadline) return 1;
            if (!b.deadline) return -1;
            return new Date(a.deadline) - new Date(b.deadline);
        });
    } else if (mode === 'priority') {
        copy.sort((a, b) => (b.priority ?? 1) - (a.priority ?? 1) || a.id - b.id);
    } else if (mode === 'name') {
        copy.sort((a, b) => a.content.localeCompare(b.content, 'ko'));
    }
    // default(등록순): 서버/드래그로 정해진 todos 배열 순서를 그대로 유지
    return copy;
}

// 통계 바
function renderStats() {
    const bar = document.getElementById('stats-bar');
    const total = todos.length;
    if (total === 0) { bar.style.display = 'none'; return; }
    bar.style.display = 'flex';
    const done = todos.filter(t => t.completed).length;
    const pct = Math.round((done / total) * 100);
    bar.innerHTML = `
        <span class="stats-text"><b>${done}</b>/${total} 완료 (${pct}%) · 남은 <b>${total - done}</b></span>
        <span class="progress-track"><span class="progress-fill" style="width:${pct}%"></span></span>
        <span class="stats-actions">
            <button class="stats-btn" onclick="completeAll()">전체 완료</button>
            <button class="stats-btn" onclick="clearCompleted()">완료 삭제</button>
        </span>`;
}

// 인라인 수정
function startEdit(id, el) {
    const todo = todos.find(t => t.id === id);
    if (!todo) return;
    const input = document.createElement('input');
    input.className = 'edit-input';
    input.value = todo.content;
    el.replaceWith(input);
    input.focus();
    input.select();
    let done = false;
    const commit = async (save) => {
        if (done) return; done = true;
        const val = input.value.trim();
        if (save && val && val !== todo.content) {
            await updateTodoField(id, { content: val });
        } else { render(); }
    };
    input.addEventListener('keydown', e => {
        if (e.key === 'Enter') commit(true);
        if (e.key === 'Escape') commit(false);
    });
    input.addEventListener('blur', () => commit(true));
}

// 일괄 처리: 실패한 항목은 유지하고, 재클릭으로 완료가 취소되지 않도록 한다.
let bulkInProgress = false;
async function completeAll() { return runBulkAction(false); }
async function clearCompleted() { return runBulkAction(true); }
async function runBulkAction(deleting) {
    if (bulkInProgress) return;
    const targets = todos.filter(t => deleting ? t.completed : !t.completed);
    if (!targets.length) return;
    if (!confirm(`${targets.length}개 항목을 ${deleting ? '삭제' : '완료 처리'}할까요?`)) return;
    const session = captureSession();
    bulkInProgress = true;
    let failures = 0;
    try {
        for (const target of targets) {
            if (!isCurrentSession(session)) return;
            try {
                await queueTodoSave(target.id, session, async () => {
                    const current = todos.find(t => t.id === target.id);
                    if (!current || (deleting ? !current.completed : current.completed)) return;
                    if (deleting) await performDelete(target.id, session);
                    else await performToggle(target.id, session);
                });
            } catch { failures++; }
        }
        if (isCurrentSession(session) && failures) {
            showAlert('todo-alert', `${failures}개 항목을 처리하지 못했어요. 연결 상태와 목록을 확인한 뒤 다시 시도해주세요.`);
        }
    } finally { if (isCurrentSession(session)) bulkInProgress = false; }
}

// =====================
// 서브태스크 (체크리스트)
// =====================
function subtaskProgress(t) {
    const subs = t.subtasks || [];
    if (subs.length === 0) return '';
    const done = subs.filter(s => s.completed).length;
    return `<span class="subtask-progress"> ${done}/${subs.length}</span>`;
}

function subtaskSection(t) {
    const subs = t.subtasks || [];
    const items = subs.map(s => `
        <li class="subtask-item ${s.completed ? 'done' : ''}">
            <div class="subtask-check ${s.completed ? 'checked' : ''}" onclick="toggleSubtask(${t.id}, ${s.id}, ${!s.completed})"></div>
            <span class="subtask-text">${escapeHtml(s.content)}</span>
            <button class="subtask-del" onclick="deleteSubtask(${t.id}, ${s.id})">✕</button>
        </li>`).join('');
    return `
        <div class="subtask-section">
            <ul class="subtask-list">${items}</ul>
            <div class="subtask-add-row">
                <input type="text" id="subtask-input-${t.id}" placeholder="하위 항목 추가..." onkeydown="if(event.key==='Enter')addSubtask(${t.id})">
                <button onclick="addSubtask(${t.id})">추가</button>
            </div>
        </div>`;
}

async function addSubtask(todoId) {
    const submitted = snapshotDrafts([`subtask-input-${todoId}`]);
    const content = document.getElementById(`subtask-input-${todoId}`).value.trim();
    if (!content || !validateTodoInput({ content })) return;
    const session = captureSession();
    return queueTodoSave(todoId, session, async () => {
        try {
            const sub = await requestJson(session, `/todos/${todoId}/subtasks`, { method: 'POST', body: JSON.stringify({ content }) });
            if (!isCurrentSession(session)) return;
            const todo = todos.find(t => t.id === todoId);
            if (todo) { todo.subtasks = todo.subtasks || []; todo.subtasks.push(sub); }
            acknowledgeDrafts(submitted);
            render();
        } catch (error) { reportRequestError(session, error); }
    });
}
async function toggleSubtask(todoId, subId, completed) {
    const session = captureSession();
    return queueTodoSave(todoId, session, async () => {
        try {
            const updated = await requestJson(session, `/subtasks/${subId}`, { method: 'PATCH', body: JSON.stringify({ completed }) });
            if (!isCurrentSession(session)) return;
            const sub = todos.find(t => t.id === todoId)?.subtasks?.find(s => s.id === subId);
            if (sub) sub.completed = updated.completed;
            render();
        } catch (error) { reportRequestError(session, error); }
    });
}
async function deleteSubtask(todoId, subId) {
    const session = captureSession();
    return queueTodoSave(todoId, session, async () => {
        try {
            await requestJson(session, `/subtasks/${subId}`, { method: 'DELETE' });
            if (!isCurrentSession(session)) return;
            const todo = todos.find(t => t.id === todoId);
            if (todo) todo.subtasks = (todo.subtasks || []).filter(s => s.id !== subId);
            render();
        } catch (error) { reportRequestError(session, error); }
    });
}

// =====================
// 드래그 정렬 (등록순 + 필터/검색 없을 때만)
// =====================
function canDrag() {
    return document.getElementById('sort-select').value === 'default'
        && currentFilter === 'all' && currentCategory === 'all'
        && !document.getElementById('search-input').value.trim();
}
let dragId = null;
function onDragStart(e, id) { dragId = id; e.currentTarget.classList.add('dragging'); }
function onDragEnd(e) { e.currentTarget.classList.remove('dragging'); document.querySelectorAll('.todo-item.drag-over').forEach(el => el.classList.remove('drag-over')); }
function onDragOver(e, id) { e.preventDefault(); }
function onDragEnter(e, id) { if (id !== dragId) e.currentTarget.classList.add('drag-over'); }
function onDragLeave(e) { e.currentTarget.classList.remove('drag-over'); }
async function onDrop(e, targetId) {
    e.preventDefault();
    e.currentTarget.classList.remove('drag-over');
    if (dragId === null || dragId === targetId) return;
    const from = todos.findIndex(t => t.id === dragId);
    const to = todos.findIndex(t => t.id === targetId);
    if (from < 0 || to < 0) return;
    const [moved] = todos.splice(from, 1);
    todos.splice(to, 0, moved);
    dragId = null;
    render();
    // Save reorder operations serially and surface failures.
    const order = todos.map(t => t.id);
    const session = captureSession();
    await queueTodoSave('order', session, async () => {
        try {
            await requestJson(session, '/todos/reorder', { method: 'POST', body: JSON.stringify({ order }) });
            if (!isCurrentSession(session)) return;
            const positions = new Map(order.map((id, index) => [id, index]));
            todos.sort((a, b) => (positions.get(a.id) ?? order.length) - (positions.get(b.id) ?? order.length));
            render();
        } catch (error) {
            reportRequestError(session, error);
            if (isCurrentSession(session)) await loadTodos();
        }
    });
}
