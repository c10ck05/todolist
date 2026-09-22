"""Todo CRUD, deadline, and ordering endpoints."""

from fastapi import APIRouter, HTTPException

from backend.dependencies import CurrentUser, DbSession
from backend.schemas import TodoCreate, TodoUpdate, DeadlineRequest, ReorderRequest, BackupImport
from backend.services.ownership import get_owned_todo
from backend.models import SubtaskTable, TodoTable, TodoRecurrenceTable
from backend.utils.todos import add_interval, normalize_repeat, subtask_dict, todo_dict


router = APIRouter()


@router.get("/todos")
def todos_get(user: CurrentUser, db: DbSession):
    user_id = user.user_id
    todos = db.query(TodoTable).filter(TodoTable.owner_id == user_id).order_by(
        TodoTable.sort_order.is_(None), TodoTable.sort_order, TodoTable.id
    ).all()
    subtasks_by_todo = {}
    if todos:
        subtasks = db.query(SubtaskTable).join(TodoTable, SubtaskTable.todo_id == TodoTable.id).filter(
            TodoTable.owner_id == user_id
        ).order_by(SubtaskTable.id).all()
        for subtask in subtasks:
            subtasks_by_todo.setdefault(subtask.todo_id, []).append(subtask_dict(subtask))
    return [todo_dict(todo, subtasks_by_todo.get(todo.id, [])) for todo in todos]


@router.post("/todos")
def create_todo(
    todo_data: TodoCreate,
    user: CurrentUser,
    db: DbSession,
):
    user_id = user.user_id
    deadline = todo_data.deadline
    category = (todo_data.category or '').strip() or None
    repeat = normalize_repeat(todo_data.repeat)
    if deadline:
        add_interval(deadline, repeat)
    new_todo = TodoTable(
        todo=todo_data.content,
        owner_id=user_id,
        deadline=deadline,
        category=category,
        repeat_cycle=repeat,
        priority=todo_data.priority,
        detail=todo_data.detail or None,
    )
    db.add(new_todo)
    db.flush()
    result = todo_dict(new_todo)
    db.commit()
    return result


@router.post("/todos/import")
def import_todos(
    data: BackupImport,
    user: CurrentUser,
    db: DbSession,
):
    """Append a complete backup atomically, assigning fresh owned IDs."""
    user_id = user.user_id
    items = sorted(data.items, key=lambda item: (item.sort_order is None, item.sort_order or 0))
    for item in items:
        if item.deadline:
            add_interval(item.deadline, item.repeat)
    existing = db.query(TodoTable).filter(TodoTable.owner_id == user_id).order_by(
        TodoTable.sort_order.is_(None), TodoTable.sort_order, TodoTable.id
    ).all()
    # Preserve the visible order of existing items and append the restored group.
    for index, todo in enumerate(existing):
        todo.sort_order = index
    imported = []
    for index, item in enumerate(items, start=len(existing)):
        todo = TodoTable(todo=item.content, owner_id=user_id, deadline=item.deadline,
                         category=(item.category or '').strip() or None,
                         repeat_cycle=normalize_repeat(item.repeat), priority=item.priority,
                         detail=item.detail, completed=item.completed, sort_order=index,
                         reminder_sent=False)
        imported.append(todo)
    db.add_all(imported)
    db.flush()
    for item, todo in zip(items, imported):
        for child in item.subtasks:
            db.add(SubtaskTable(todo_id=todo.id, content=child.content, completed=child.completed))
    db.commit()
    return {'imported': len(items)}


@router.delete("/todos/{id}")
def delete_todo(
    id: int,
    user: CurrentUser,
    db: DbSession,
):
    user_id = user.user_id
    todo = db.query(TodoTable).filter(TodoTable.id == id).first()
    if not todo:
        raise HTTPException(status_code=404, detail="해당 투두를 찾을 수 없습니다.")
    if user_id != todo.owner_id:
        raise HTTPException(status_code=400, detail="본인 것만 삭제할 수 있습니다.")
    db.delete(todo)
    db.query(SubtaskTable).filter(SubtaskTable.todo_id == id).delete(synchronize_session=False)
    db.query(TodoRecurrenceTable).filter(TodoRecurrenceTable.source_id == id).delete()
    db.commit()
    return {"message": "삭제 완료"}


@router.patch("/todos/{id}/toggle")
def toggle_todo(
    id: int,
    user: CurrentUser,
    db: DbSession,
):
    user_id = user.user_id
    todo = get_owned_todo(id, user_id, db, lock=True)
    todo.completed = not todo.completed
    spawned = None
    if todo.completed and todo.deadline and db.get(TodoRecurrenceTable, id) is None:
        next_deadline = add_interval(todo.deadline, todo.repeat_cycle)
        if next_deadline:
            spawned = TodoTable(
                todo=todo.todo,
                owner_id=todo.owner_id,
                deadline=next_deadline,
                category=todo.category,
                repeat_cycle=todo.repeat_cycle,
                priority=todo.priority,
                detail=todo.detail,
                completed=False,
                reminder_sent=False,
            )
            db.add(spawned)
            db.flush()
            db.add(TodoRecurrenceTable(source_id=id, successor_id=spawned.id))
    result = {"id": todo.id, "completed": todo.completed}
    if spawned:
        result["spawned"] = todo_dict(spawned)
    db.commit()
    return result


@router.patch("/todos/{id}")
def update_todo(
    id: int,
    data: TodoUpdate,
    user: CurrentUser,
    db: DbSession,
):
    user_id = user.user_id
    todo = get_owned_todo(id, user_id, db)
    data = data.model_dump(exclude_unset=True)
    if todo.deadline and 'repeat' in data:
        add_interval(todo.deadline, data['repeat'])
    if "content" in data:
        todo.todo = data['content']
    if "category" in data:
        category = data.get("category")
        todo.category = (category.strip() or None) if category else None
    if "repeat" in data:
        todo.repeat_cycle = normalize_repeat(data.get("repeat"))
    if "priority" in data:
        todo.priority = data['priority']
    if "detail" in data:
        detail = data.get("detail")
        todo.detail = (detail.strip() or None) if detail else None
    subtasks = db.query(SubtaskTable).filter(SubtaskTable.todo_id == id).order_by(SubtaskTable.id).all()
    result = todo_dict(todo, [subtask_dict(subtask) for subtask in subtasks])
    db.commit()
    return result


@router.patch("/todos/{id}/deadline")
def update_deadline(
    id: int,
    data: DeadlineRequest,
    user: CurrentUser,
    db: DbSession,
):
    user_id = user.user_id
    todo = get_owned_todo(id, user_id, db)
    if data.deadline:
        add_interval(data.deadline, todo.repeat_cycle)
    todo.deadline = data.deadline
    todo.reminder_sent = False
    result = {
        "id": todo.id,
        "deadline": todo.deadline.isoformat() if todo.deadline else None,
    }
    db.commit()
    return result


@router.post("/todos/reorder")
def reorder_todos(
    data: ReorderRequest,
    user: CurrentUser,
    db: DbSession,
):
    user_id = user.user_id
    order = data.order
    todos = db.query(TodoTable).filter(TodoTable.owner_id == user_id, TodoTable.id.in_(order)).all()
    todo_map = {todo.id: todo for todo in todos}
    for index, todo_id in enumerate(order):
        todo = todo_map.get(todo_id)
        if todo:
            todo.sort_order = index
    db.commit()
    return {"message": "순서가 저장되었습니다."}
