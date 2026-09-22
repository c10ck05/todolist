// =====================
// 리스트 렌더링
// =====================
// 현재 존재하는 카테고리 목록 (사용 중인 카테고리들)
function getCategories() {
    return [...new Set(todos.map(t => t.category).filter(Boolean))].sort();
}

function repeatOptions(selected) {
    selected = selected?.type === 'weekly' && selected.days?.length ? 'custom' : (typeof selected === 'string' ? selected : (selected?.type || 'none'));
    return Object.entries({ ...REPEAT_LABELS, custom: '사용자 설정' }).map(([val, label]) =>
        `<option value="${val}" ${val === (selected || 'none') ? 'selected' : ''}>${val === 'none' ? '없음' : label}</option>`
    ).join('');
}

const WEEKDAYS = { mon: '월', tue: '화', wed: '수', thu: '목', fri: '금', sat: '토', sun: '일' };
function repeatLabel(value) {
    const repeat = typeof value === 'string' ? { type: value } : (value || { type: 'none' });
    if (repeat.type === 'weekly' && repeat.days?.length) {
        return `매주 ${repeat.days.map(day => WEEKDAYS[day]).filter(Boolean).join('·')}`;
    }
    if (repeat.type === 'interval') return `${repeat.value}일마다`;
    return REPEAT_LABELS[repeat.type] || '';
}
function repeatEditor(todo) {
    const repeat = typeof todo.repeat === 'string' ? { type: todo.repeat } : (todo.repeat || { type: 'none' });
    const days = repeat.days || [];
    return `<div class="repeat-editor">
        <select id="repeat-input-${todo.id}" aria-label="반복 주기" onchange="changeRepeatType(${todo.id}, this.value)">${repeatOptions(repeat)}</select>
        <input type="number" min="1" max="3650" step="1" id="repeat-interval-${todo.id}" aria-label="반복 간격 (1~3650일)" value="${Number.isInteger(repeat.value) ? repeat.value : 1}" ${repeat.type === 'interval' ? '' : 'hidden'}>
        <div class="repeat-custom" id="repeat-custom-${todo.id}" ${repeat.type === 'weekly' && days.length ? '' : 'hidden'}>
            <div class="detail-section-title">반복할 요일을 선택하세요</div>
            <div class="repeat-days" id="repeat-days-${todo.id}">
                ${Object.entries(WEEKDAYS).map(([day, label]) => `<label class="repeat-day"><input id="repeat-day-${todo.id}-${day}" type="checkbox" value="${day}" ${days.includes(day) ? 'checked' : ''}><span>${label}</span></label>`).join('')}
            </div>
        </div>
        <button class="btn-deadline-save" onclick="saveRepeat(${todo.id})">반복 저장</button>
        <small>마감기한을 설정하면 완료 시 다음 반복 일정이 생성됩니다.</small>
    </div>`;
}

// 카테고리 필터 칩 + 입력 자동완성(datalist) 갱신
function renderCategoryChips() {
    const cats = getCategories();
    const container = document.getElementById('category-filters');
    if (cats.length === 0) { container.innerHTML = ''; currentCategory = 'all'; }
    else {
        const chips = [['all', '전체 카테고리'], ...cats.map(c => [c, c]), ['none', '미분류']];
        container.replaceChildren(...chips.map(([val, label]) => {
            const button = document.createElement('button');
            button.className = `tab-btn ${currentCategory === val ? 'active' : ''}`;
            button.textContent = label;
            button.addEventListener('click', () => filterByCategory(val, button));
            return button;
        }));
    }
    document.getElementById('category-list').innerHTML = cats.map(c => `<option value="${escapeHtml(c)}">`).join('');
}

function filterByCategory(category, btn) {
    currentCategory = category;
    document.querySelectorAll('#category-filters .tab-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    render();
}

const detailDrafts = new Map();
function rememberDetailDraft(event) {
    const el = event.target;
    if (!el.id || !el.closest('.deadline-panel') || !el.matches('input, select, textarea')) return;
    detailDrafts.set(el.id, el.type === 'checkbox' ? el.checked : el.value);
}
document.addEventListener('input', rememberDetailDraft, true);
document.addEventListener('change', rememberDetailDraft, true);
function snapshotDrafts(fields) {
    return fields.map(id => [id, detailDrafts.get(id)]);
}
function acknowledgeDrafts(submitted) {
    submitted.forEach(([id, value]) => {
        if (detailDrafts.get(id) === value) detailDrafts.delete(id);
    });
}
function restoreDetailDrafts() {
    detailDrafts.forEach((value, id) => {
        const el = document.getElementById(id);
        if (!el) return;
        if (el.type === 'checkbox') el.checked = value;
        else el.value = value;
    });
    todos.forEach(todo => {
        const select = document.getElementById(`repeat-input-${todo.id}`);
        if (select) changeRepeatType(todo.id, select.value);
    });
}
function render() {
    renderCategoryChips();
    if (viewMode === 'timeline') { renderTimeline(); return; }
    if (viewMode === 'calendar') { renderCalendar(); return; }
    renderStats();
    const list = document.getElementById('todo-list');
    const q = document.getElementById('search-input').value.trim().toLowerCase();
    let filtered = todos;
    if (currentFilter === 'active')    filtered = filtered.filter(t => !t.completed);
    if (currentFilter === 'completed') filtered = filtered.filter(t => t.completed);
    if (currentFilter === 'overdue')   filtered = filtered.filter(t => isOverdue(t));
    if (currentCategory === 'none')     filtered = filtered.filter(t => !t.category);
    else if (currentCategory !== 'all') filtered = filtered.filter(t => t.category === currentCategory);
    if (q) filtered = filtered.filter(t => t.content.toLowerCase().includes(q));
    filtered = applySort(filtered);
    if (filtered.length === 0) {
        const msg = q ? `'${escapeHtml(q)}' 검색 결과가 없어요.`
            : ({ all: '할 일을 추가해보세요!', active: '할 일이 없어요!', completed: '완료된 항목이 없어요!', overdue: '마감 초과된 항목이 없어요! ' }[currentFilter] || '할 일을 추가해보세요!');
        list.innerHTML = `<div class="empty-state"><p>${msg}</p></div>`;
        return;
    }
    const dragEnabled = canDrag();
    list.innerHTML = filtered.map(t => {
        const overdue = isOverdue(t);
        const chipHtml = t.deadline
            ? `<span class="deadline-chip ${overdue ? 'overdue' : ''}">${formatDeadline(t.deadline)}</span>`
            : '';
        const catHtml = t.category ? `<span class="category-badge"> ${escapeHtml(t.category)}</span>` : '';
        const repeatHtml = repeatLabel(t.repeat) ? `<span class="repeat-icon"> ${escapeHtml(repeatLabel(t.repeat))}</span>` : '';
        const memoHtml = t.detail ? `<span class="memo-icon" title="${escapeHtml(t.detail)}">메모</span>` : '';
        const dragAttrs = dragEnabled
            ? `draggable="true" ondragstart="onDragStart(event, ${t.id})" ondragend="onDragEnd(event)" ondragover="onDragOver(event, ${t.id})" ondragenter="onDragEnter(event, ${t.id})" ondragleave="onDragLeave(event)" ondrop="onDrop(event, ${t.id})"`
            : '';
        const handleHtml = dragEnabled ? `<span class="drag-handle" title="드래그하여 순서 변경">⠿</span>` : '';
        return `
        <li class="todo-item ${t.completed ? 'completed' : ''} ${overdue ? 'overdue' : ''}" ${dragAttrs}>
            <div class="todo-item-main">
                ${handleHtml}
                <div class="todo-checkbox ${t.completed ? 'checked' : ''}" onclick="toggleTodo(${t.id})"></div>
                <div class="todo-content">
                    <div class="todo-text" ondblclick="startEdit(${t.id}, this)" title="더블클릭하여 수정">${escapeHtml(t.content)}${repeatHtml}${memoHtml}${subtaskProgress(t)}</div>
                    ${chipHtml}${ddayBadge(t.deadline, t.completed)}${priorityBadge(t.priority)}${catHtml}
                </div>
                <div class="todo-actions">
                    <button class="btn-deadline" id="btn-deadline-${t.id}" title="세부 설정" aria-label="세부 설정" aria-controls="deadline-panel-${t.id}" aria-expanded="false" onclick="toggleDeadlinePanel(${t.id})"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" aria-hidden="true"><path d="M4 7h9m4 0h3M4 17h3m4 0h9"/><circle cx="15" cy="7" r="2"/><circle cx="9" cy="17" r="2"/></svg></button>
                    <button class="btn-delete" onclick="deleteTodo(${t.id})">삭제</button>
                </div>
            </div>
            <div class="deadline-panel" id="deadline-panel-${t.id}">
                <div class="detail-section detail-basic">
                <div class="detail-field">
                <label for="category-input-${t.id}">카테고리</label>
                <input type="text" list="category-list" id="category-input-${t.id}" value="${escapeHtml(t.category || '')}" placeholder="없음" onchange="updateCategory(${t.id}, this.value)">
                </div><div class="detail-field">
                <label for="priority-input-${t.id}">우선순위</label>
                <select id="priority-input-${t.id}" onchange="updatePriority(${t.id}, this.value)">${priorityOptions(t.priority)}</select>
                </div></div>
                <div class="detail-section">
                <label class="detail-section-title" for="repeat-input-${t.id}">반복 일정</label>
                ${repeatEditor(t)}
                </div>
                <div class="detail-section">
                <label class="detail-section-title" for="deadline-input-${t.id}">마감기한</label>
                <div class="detail-deadline-row">
                <input type="datetime-local" id="deadline-input-${t.id}" value="${escapeHtml((t.deadline || '').slice(0, 16))}">
                <button class="btn-deadline-save" onclick="saveDeadline(${t.id})">저장</button>
                ${t.deadline ? `<button class="btn-deadline-remove" onclick="removeDeadline(${t.id})">제거</button>` : ''}
                </div></div>
                <div class="detail-section">
                <label class="detail-section-title" for="detail-input-${t.id}">메모 · 자동 저장</label>
                <textarea id="detail-input-${t.id}" placeholder="메모 (자동 저장)" onchange="updateDetail(${t.id}, this.value)">${escapeHtml(t.detail || '')}</textarea>
                </div>
                <div class="detail-section">
                <div class="detail-section-title">체크리스트</div>
                ${subtaskSection(t)}
                </div>
            </div>
        </li>`;
    }).join('');
    applyOpenPanels();
    restoreDetailDrafts();
}

// =====================
// 타임라인 렌더링
// =====================
function renderTimeline() {
    const view = document.getElementById('timeline-view');
    const todosWithDeadline = [...todos]
        .filter(t => t.deadline)
        .sort((a, b) => new Date(a.deadline) - new Date(b.deadline));
    if (todosWithDeadline.length === 0) {
        view.innerHTML = `<div class="timeline-empty"><p>마감기한이 설정된 할 일이 없어요!<br>할 일의 세부 설정 버튼으로 마감기한을 추가해보세요.</p></div>`;
        return;
    }
    const now = new Date();
    const todayStr = now.toDateString();
    const groups = {};
    todosWithDeadline.forEach(t => {
        const key = new Date(t.deadline).toDateString();
        if (!groups[key]) groups[key] = [];
        groups[key].push(t);
    });
    let html = '';
    Object.entries(groups).forEach(([dateStr, items]) => {
        const groupDate = new Date(dateStr);
        const isPast = groupDate < new Date(now.toDateString());
        const isToday = dateStr === todayStr;
        const labelClass = isPast ? 'overdue-label' : (isToday ? 'today-label' : '');
        const dateLabel = isToday
            ? '오늘'
            : isPast
                ? `${groupDate.getMonth() + 1}/${groupDate.getDate()} (지남)`
                : `${groupDate.getMonth() + 1}월 ${groupDate.getDate()}일`;
        html += `<div class="timeline-group">
            <div class="timeline-date-label ${labelClass}">${dateLabel}</div>`;
        items.forEach(t => {
            const d = new Date(t.deadline);
            const timeStr = `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`;
            const overdue = isOverdue(t);
            const dotClass  = t.completed ? 'done' : (overdue ? 'overdue' : (isToday ? 'today' : ''));
            const cardClass = t.completed ? 'done' : (overdue ? 'overdue' : '');
            let badge = '';
            if (t.completed)   badge = `<span class="timeline-badge done-badge">✓ 완료</span>`;
            else if (overdue)  badge = `<span class="timeline-badge overdue-badge"> 마감 초과</span>`;
            else if (isToday)  badge = `<span class="timeline-badge today-badge">오늘 마감</span>`;
            html += `
            <div class="timeline-item">
                <div class="timeline-line-col">
                    <div class="timeline-dot ${dotClass}"></div>
                </div>
                <div class="timeline-card ${cardClass}">
                    <div class="timeline-card-header">
                        <span class="timeline-card-text">${escapeHtml(t.content)}</span>
                        <span class="timeline-time">${timeStr}</span>
                    </div>
                    ${badge}
                </div>
            </div>`;
        });
        html += `</div>`;
    });
    view.innerHTML = html;
}

// =====================
// 캘린더 렌더링 (월간)
// =====================
function dateKey(d) {
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function renderCalendar() {
    const view = document.getElementById('calendar-view');
    const year = calendarDate.getFullYear();
    const month = calendarDate.getMonth();
    const first = new Date(year, month, 1);
    const startDow = first.getDay();
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    const todayKey = dateKey(new Date());

    // 날짜별 할 일 묶기
    const byDay = {};
    todos.filter(t => t.deadline).forEach(t => {
        const key = dateKey(new Date(t.deadline));
        (byDay[key] = byDay[key] || []).push(t);
    });

    const dows = ['일', '월', '화', '수', '목', '금', '토'];
    let cells = dows.map((d, i) => `<div class="cal-dow ${i === 0 ? 'sun' : (i === 6 ? 'sat' : '')}">${d}</div>`).join('');
    for (let i = 0; i < startDow; i++) cells += `<div class="cal-cell empty"></div>`;
    for (let day = 1; day <= daysInMonth; day++) {
        const d = new Date(year, month, day);
        const key = dateKey(d);
        const dow = d.getDay();
        const items = byDay[key] || [];
        const dots = items.slice(0, 4).map(t => {
            const cls = t.completed ? 'done' : (isOverdue(t) ? 'overdue' : '');
            return `<span class="cal-dot ${cls}"></span>`;
        }).join('');
        const more = items.length > 4 ? `<span class="cal-more">+${items.length - 4}</span>` : '';
        const cls = [key === todayKey ? 'today' : '', key === selectedCalKey ? 'selected' : ''].join(' ');
        const numCls = dow === 0 ? 'sun' : (dow === 6 ? 'sat' : '');
        cells += `<div class="cal-cell ${cls}" onclick="selectCalDay('${key}')">
            <div class="cal-daynum ${numCls}">${day}</div>
            <div class="cal-dot-row">${dots}${more}</div>
        </div>`;
    }

    let selectedHtml = '';
    if (selectedCalKey && byDay[selectedCalKey]) {
        const [sy, sm, sd] = selectedCalKey.split('-');
        selectedHtml = `<div class="cal-selected-list">
            <div class="cal-selected-title"> ${parseInt(sm)}월 ${parseInt(sd)}일 (${byDay[selectedCalKey].length}건)</div>
            ${byDay[selectedCalKey].sort((a, b) => new Date(a.deadline) - new Date(b.deadline)).map(t => {
                const dt = new Date(t.deadline);
                const time = `${String(dt.getHours()).padStart(2, '0')}:${String(dt.getMinutes()).padStart(2, '0')}`;
                const overdue = isOverdue(t);
                return `<li class="todo-item" style="list-style:none;margin-bottom:6px;">
                    <div class="todo-item-main">
                        <div class="todo-checkbox ${t.completed ? 'checked' : ''}" onclick="toggleTodo(${t.id})"></div>
                        <div class="todo-content">
                            <div class="todo-text ${t.completed ? '' : ''}">${escapeHtml(t.content)}</div>
                            <span class="deadline-chip ${overdue ? 'overdue' : ''}"> ${time}</span>${priorityBadge(t.priority)}${t.category ? `<span class="category-badge"> ${escapeHtml(t.category)}</span>` : ''}
                        </div>
                    </div>
                </li>`;
            }).join('')}
        </div>`;
    }

    view.innerHTML = `
        <div class="cal-header">
            <div class="cal-title">${year}년 ${month + 1}월</div>
            <div class="cal-nav">
                <button onclick="calNav(-1)">‹</button>
                <button onclick="calToday()">오늘</button>
                <button onclick="calNav(1)">›</button>
            </div>
        </div>
        <div class="cal-grid">${cells}</div>
        ${selectedHtml}`;
}

function calNav(delta) {
    calendarDate = new Date(calendarDate.getFullYear(), calendarDate.getMonth() + delta, 1);
    renderCalendar();
}
function calToday() {
    calendarDate = new Date();
    selectedCalKey = dateKey(new Date());
    renderCalendar();
}
function selectCalDay(key) {
    selectedCalKey = (selectedCalKey === key) ? null : key;
    renderCalendar();
}

function escapeHtml(str) {
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
