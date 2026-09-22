"""Shared FastAPI dependencies."""

from typing import Annotated

import jwt
import hmac
from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from backend.config import JWT_ALGORITHM, JWT_SECRET_KEY
from backend.database import SessionLocal
from backend.models import UserTable
from backend.security import password_version


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(db: DbSession, authorization: Annotated[str | None, Header()] = None):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="인증 정보가 없습니다.")

    token = authorization[7:]
    try:
        decoded_payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM],
                                     options={"require": ["sub", "exp", "ver"]})
        user_id = decoded_payload.get("sub")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="토큰이 만료되었습니다.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")
    user = db.query(UserTable).filter(UserTable.user_id == user_id).first()
    version = decoded_payload.get('ver')
    if not user or not isinstance(version, str) or not hmac.compare_digest(version, password_version(user.password)):
        raise HTTPException(status_code=401, detail="로그인이 만료되었습니다. 다시 로그인해주세요.")
    return user


CurrentUser = Annotated[UserTable, Depends(get_current_user)]
