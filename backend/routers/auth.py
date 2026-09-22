"""Authentication and email-verification endpoints."""

import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import APIRouter, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from backend.config import JWT_ALGORITHM, JWT_SECRET_KEY, KST
from backend.dependencies import DbSession
from backend.models import EmailVerificationTable, UserTable
from backend.services.email import send_email
from backend.security import auth_limit, password_version
from backend.schemas import EmailRequest, SignupRequest, LoginRequest, ResetPasswordRequest


router = APIRouter()


def consume_verification(db: Session, verification, input_code: str):
    """Claim a code exactly once, in the same transaction as the account change."""
    removed = db.query(EmailVerificationTable).filter(
        EmailVerificationTable.email == verification.email,
        EmailVerificationTable.purpose == verification.purpose,
        EmailVerificationTable.code == input_code,
        EmailVerificationTable.expires_at == verification.expires_at,
        EmailVerificationTable.expires_at > datetime.now(KST).replace(tzinfo=None),
    ).delete(synchronize_session=False)
    if removed != 1:
        db.rollback()
        raise HTTPException(400, '이미 사용되었거나 만료된 인증번호입니다. 다시 요청해주세요.')


def issue_verification(db: Session, email: str, purpose: str):
    code = str(secrets.randbelow(900000) + 100000)
    expires_at = datetime.now(KST).replace(tzinfo=None) + timedelta(minutes=3)
    db.query(EmailVerificationTable).filter_by(email=email, purpose=purpose).delete()
    db.add(EmailVerificationTable(email=email, purpose=purpose, code=code, expires_at=expires_at))
    db.commit()
    label = "회원가입" if purpose == "signup" else "비밀번호 재설정"
    send_email(to=email, subject=f"투두리스트 {label} 인증번호입니다.",
               body=f"요청하신 인증번호는 [{code}] 입니다. 3분 내에 입력해주세요.")
    return {"message": "인증번호가 발송되었습니다."}


def find_verification(db: Session, email: str, purpose: str, code: str):
    verification = db.get(EmailVerificationTable, (email, purpose))
    if not verification:
        raise HTTPException(400, "인증번호 요청을 먼저 진행해주세요.")
    if datetime.now(KST).replace(tzinfo=None) > verification.expires_at:
        raise HTTPException(400, "인증 시간이 만료되었습니다.")
    if verification.code != code:
        raise HTTPException(400, "인증번호가 일치하지 않습니다.")
    return verification


@router.post("/request-code")
def request_verification_code(data: EmailRequest, request: Request, db: DbSession):
    auth_limit(request, data.email, 'send')
    return issue_verification(db, data.email, 'signup')


@router.post("/signup")
def signup_todo(data: SignupRequest, request: Request, db: DbSession):
    auth_limit(request, data.email, 'verify')
    verification = find_verification(db, data.email, 'signup', data.code)
    if db.query(UserTable.id).filter(UserTable.user_id == data.username).first():
        raise HTTPException(400, "이미 해당 ID가 있습니다.")
    hashed = bcrypt.hashpw(data.password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    consume_verification(db, verification, data.code)
    db.add(UserTable(user_id=data.username, password=hashed, email=data.email))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "이미 사용 중인 아이디 또는 이메일입니다.")
    return {"message": "회원가입 성공!"}


@router.post("/login")
def login_todo(data: LoginRequest, request: Request, db: DbSession):
    auth_limit(request, data.username, 'login')
    user = db.query(UserTable).filter(UserTable.user_id == data.username).first()
    if not user:
        raise HTTPException(404, "ID가 맞지 않습니다.")
    if not bcrypt.checkpw(data.password.encode("utf-8"), user.password.encode("utf-8")):
        raise HTTPException(401, "비밀번호가 맞지 않습니다.")
    payload = {
        "sub": user.user_id,
        "ver": password_version(user.password),
        "exp": datetime.now(timezone.utc) + timedelta(days=7),
    }
    return {"access_token": jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)}


@router.post("/request-reset-code")
def request_reset_code(data: EmailRequest, request: Request, db: DbSession):
    auth_limit(request, data.email, 'send')
    if not db.query(UserTable.id).filter(UserTable.email == data.email).first():
        raise HTTPException(400, "회원가입이 필요합니다.")
    return issue_verification(db, data.email, 'reset')


@router.post("/reset-password")
def reset_password(data: ResetPasswordRequest, request: Request, db: DbSession):
    auth_limit(request, data.email, 'verify')
    user = db.query(UserTable).filter(UserTable.email == data.email).first()
    if not user:
        raise HTTPException(400, "일치하는 계정이 없습니다.")
    verification = find_verification(db, data.email, 'reset', data.code)
    hashed = bcrypt.hashpw(data.new_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    consume_verification(db, verification, data.code)
    user.password = hashed
    db.commit()
    return {"message": "비밀번호 변경이 완료되었습니다."}
