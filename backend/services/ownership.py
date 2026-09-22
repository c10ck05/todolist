"""Shared ownership checks, independent of HTTP router modules."""

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.models import TodoTable, SubtaskTable


def get_owned_todo(todo_id: int, user_id: str, db: Session, *, lock=False):
    query = db.query(TodoTable).filter(TodoTable.id == todo_id)
    todo = (query.with_for_update() if lock else query).first()
    if not todo:
        raise HTTPException(404, '데이터가 없습니다.')
    if todo.owner_id != user_id:
        raise HTTPException(403, '본인 리스트가 아닙니다.')
    return todo


def get_owned_subtask(subtask_id: int, user_id: str, db: Session):
    row = db.query(SubtaskTable, TodoTable.owner_id).join(
        TodoTable, SubtaskTable.todo_id == TodoTable.id
    ).filter(SubtaskTable.id == subtask_id).first()
    if not row:
        raise HTTPException(404, '데이터가 없습니다.')
    subtask, owner_id = row
    if owner_id != user_id:
        raise HTTPException(403, '본인 리스트가 아닙니다.')
    return subtask
