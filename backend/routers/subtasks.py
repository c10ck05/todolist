"""Subtask endpoints."""

from fastapi import APIRouter

from backend.dependencies import CurrentUser, DbSession
from backend.schemas import SubtaskCreate, SubtaskUpdate
from backend.models import SubtaskTable
from backend.services.ownership import get_owned_todo, get_owned_subtask
from backend.utils.todos import subtask_dict


router = APIRouter()


@router.post("/todos/{id}/subtasks")
def create_subtask(
    id: int,
    data: SubtaskCreate,
    user: CurrentUser,
    db: DbSession,
):
    user_id = user.user_id
    get_owned_todo(id, user_id, db)
    content = data.content
    subtask = SubtaskTable(todo_id=id, content=content, completed=False)
    db.add(subtask)
    db.flush()
    result = subtask_dict(subtask)
    db.commit()
    return result


@router.patch("/subtasks/{sid}")
def update_subtask(
    sid: int,
    data: SubtaskUpdate,
    user: CurrentUser,
    db: DbSession,
):
    user_id = user.user_id
    subtask = get_owned_subtask(sid, user_id, db)
    data = data.model_dump(exclude_unset=True)
    if "completed" in data:
        subtask.completed = data['completed']
    if "content" in data:
        subtask.content = data['content']
    result = subtask_dict(subtask)
    db.commit()
    return result


@router.delete("/subtasks/{sid}")
def delete_subtask(
    sid: int,
    user: CurrentUser,
    db: DbSession,
):
    user_id = user.user_id
    subtask = get_owned_subtask(sid, user_id, db)
    db.delete(subtask)
    db.commit()
    return {"message": "삭제 완료"}
