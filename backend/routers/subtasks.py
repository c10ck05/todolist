"""Subtask endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from backend.dependencies import get_current_user_id, get_db
from backend.schemas import SubtaskCreate, SubtaskUpdate
from backend.models import SubtaskTable
from backend.routers.todos import get_owned_todo
from backend.utils.todos import subtask_dict


router = APIRouter()


@router.post("/todos/{id}/subtasks")
def create_subtask(
    id: int,
    data: SubtaskCreate,
    authorization: Annotated[str | None, Header()] = None,
    db: Session = Depends(get_db),
):
    user_id = get_current_user_id(authorization)
    get_owned_todo(id, user_id, db)
    content = data.content
    if not content:
        raise HTTPException(status_code=400, detail="내용을 입력해주세요.")
    subtask = SubtaskTable(todo_id=id, content=content, completed=False)
    db.add(subtask)
    db.commit()
    db.refresh(subtask)
    return subtask_dict(subtask)


@router.patch("/subtasks/{sid}")
def update_subtask(
    sid: int,
    data: SubtaskUpdate,
    authorization: Annotated[str | None, Header()] = None,
    db: Session = Depends(get_db),
):
    user_id = get_current_user_id(authorization)
    subtask = db.query(SubtaskTable).filter(SubtaskTable.id == sid).first()
    if not subtask:
        raise HTTPException(status_code=404, detail="데이터가 없습니다.")
    get_owned_todo(subtask.todo_id, user_id, db)
    data = data.model_dump(exclude_unset=True)
    if "completed" in data:
        subtask.completed = bool(data.get("completed"))
    if "content" in data:
        content = (data.get("content") or "").strip()
        if content:
            subtask.content = content
    db.commit()
    return subtask_dict(subtask)


@router.delete("/subtasks/{sid}")
def delete_subtask(
    sid: int,
    authorization: Annotated[str | None, Header()] = None,
    db: Session = Depends(get_db),
):
    user_id = get_current_user_id(authorization)
    subtask = db.query(SubtaskTable).filter(SubtaskTable.id == sid).first()
    if not subtask:
        raise HTTPException(status_code=404, detail="데이터가 없습니다.")
    get_owned_todo(subtask.todo_id, user_id, db)
    db.delete(subtask)
    db.commit()
    return {"message": "삭제 완료"}
