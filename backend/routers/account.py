"""Account management endpoints."""

from typing import Annotated

import bcrypt
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from backend.dependencies import get_current_user_id, get_db
from backend.schemas import ChangePasswordRequest, DeleteAccountRequest
from backend.security import auth_limit
from backend.models import EmailVerificationTable, SubtaskTable, TodoTable, UserTable, TodoRecurrenceTable


router = APIRouter()


@router.post("/change-password")
def change_password(
    data: ChangePasswordRequest,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    db: Session = Depends(get_db),
):
    data = data.model_dump()
    user_id = get_current_user_id(authorization)
    auth_limit(request, user_id, 'password_check')
    user = db.query(UserTable).filter(UserTable.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    current = (data.get("current_password") or "").encode("utf-8")
    if not bcrypt.checkpw(current, user.password.encode("utf-8")):
        raise HTTPException(status_code=400, detail="현재 비밀번호가 일치하지 않습니다.")
    new_password = data.get("new_password") or ""
    user.password = bcrypt.hashpw(new_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    db.commit()
    return {"message": "비밀번호가 변경되었습니다."}


@router.delete("/account")
def delete_account(
    data: DeleteAccountRequest,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    db: Session = Depends(get_db),
):
    user_id = get_current_user_id(authorization)
    user = db.query(UserTable).filter(UserTable.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    auth_limit(request, user_id, 'password_check')
    password = data.password.encode("utf-8")
    if not bcrypt.checkpw(password, user.password.encode("utf-8")):
        raise HTTPException(status_code=400, detail="비밀번호가 일치하지 않습니다.")

    todo_ids = [todo.id for todo in db.query(TodoTable).filter(TodoTable.owner_id == user_id).all()]
    if todo_ids:
        db.query(TodoRecurrenceTable).filter(TodoRecurrenceTable.source_id.in_(todo_ids)).delete(synchronize_session=False)
        db.query(SubtaskTable).filter(SubtaskTable.todo_id.in_(todo_ids)).delete(synchronize_session=False)
    db.query(TodoTable).filter(TodoTable.owner_id == user_id).delete(synchronize_session=False)
    db.query(EmailVerificationTable).filter(EmailVerificationTable.email == user.email).delete(
        synchronize_session=False
    )
    db.delete(user)
    db.commit()
    return {"message": "계정이 삭제되었습니다."}
