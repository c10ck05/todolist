"""Account management endpoints."""

import bcrypt
from fastapi import APIRouter, HTTPException, Request

from backend.dependencies import CurrentUser, DbSession
from backend.schemas import ChangePasswordRequest, DeleteAccountRequest
from backend.security import auth_limit
from backend.models import EmailVerificationTable, SubtaskTable, TodoTable, TodoRecurrenceTable


router = APIRouter()


@router.post("/change-password")
def change_password(
    data: ChangePasswordRequest,
    request: Request,
    user: CurrentUser,
    db: DbSession,
):
    user_id = user.user_id
    auth_limit(request, user_id, 'password_check')
    current = data.current_password.encode("utf-8")
    if not bcrypt.checkpw(current, user.password.encode("utf-8")):
        raise HTTPException(status_code=400, detail="현재 비밀번호가 일치하지 않습니다.")
    user.password = bcrypt.hashpw(data.new_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    db.commit()
    return {"message": "비밀번호가 변경되었습니다."}


@router.delete("/account")
def delete_account(
    data: DeleteAccountRequest,
    request: Request,
    user: CurrentUser,
    db: DbSession,
):
    user_id = user.user_id
    auth_limit(request, user_id, 'password_check')
    password = data.password.encode("utf-8")
    if not bcrypt.checkpw(password, user.password.encode("utf-8")):
        raise HTTPException(status_code=400, detail="비밀번호가 일치하지 않습니다.")

    todo_ids = db.query(TodoTable.id).filter(TodoTable.owner_id == user_id)
    db.query(TodoRecurrenceTable).filter(TodoRecurrenceTable.source_id.in_(todo_ids)).delete(synchronize_session=False)
    db.query(SubtaskTable).filter(SubtaskTable.todo_id.in_(todo_ids)).delete(synchronize_session=False)
    db.query(TodoTable).filter(TodoTable.owner_id == user_id).delete(synchronize_session=False)
    db.query(EmailVerificationTable).filter(EmailVerificationTable.email == user.email).delete(
        synchronize_session=False
    )
    db.delete(user)
    db.commit()
    return {"message": "계정이 삭제되었습니다."}
