"""Authentication and email-verification endpoints."""

import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from backend.config import JWT_ALGORITHM, JWT_SECRET_KEY, KST
from backend.dependencies import get_db
from backend.models import EmailVerificationTable, UserTable
from backend.services.email import send_email
from backend.security import auth_limit, password_version
from backend.schemas import EmailRequest, SignupRequest, LoginRequest, ResetPasswordRequest


router = APIRouter()


@router.post("/request-code")
def request_verification_code(email_data: EmailRequest, request: Request, db: Session = Depends(get_db)):
    email_data = email_data.model_dump()
    user_email = email_data.get("email")
    if not isinstance(user_email, str) or not user_email:
        raise HTTPException(status_code=400, detail="이메일을 입력해주세요.")

    auth_limit(request, user_email, 'send')
    code = str(secrets.randbelow(900000) + 100000)
    expire_time = datetime.now(KST).replace(tzinfo=None) + timedelta(minutes=3)
    db.query(EmailVerificationTable).filter(EmailVerificationTable.email == user_email,
                                           EmailVerificationTable.purpose == 'signup').delete()
    db.add(EmailVerificationTable(email=user_email, purpose='signup', code=code, expires_at=expire_time))
    db.commit()
    send_email(
        to=user_email,
        subject="투두리스트 회원가입 인증번호입니다.",
        body=f"요청하신 인증번호는 [{code}] 입니다. 3분 내에 입력해주세요.",
    )
    return {"message": "인증번호가 발송되었습니다."}


@router.post("/signup")
def signup_todo(user_data: SignupRequest, request: Request, db: Session = Depends(get_db)):
    user_data = user_data.model_dump()
    user_id = user_data.get("username")
    raw_password = user_data.get("password")
    user_email = user_data.get("email")
    input_code = user_data.get("code")
    if not isinstance(user_email, str) or not user_email:
        raise HTTPException(400, '이메일을 입력해주세요.')
    auth_limit(request, user_email, 'verify')

    verification = db.query(EmailVerificationTable).filter(
        EmailVerificationTable.email == user_email,
        EmailVerificationTable.purpose == 'signup',
    ).first()
    if not verification:
        raise HTTPException(status_code=400, detail="인증번호 요청을 먼저 진행해주세요.")
    if datetime.now(KST).replace(tzinfo=None) > verification.expires_at:
        db.delete(verification)
        db.commit()
        raise HTTPException(status_code=400, detail="인증 시간이 만료되었습니다.")
    if verification.code != input_code:
        raise HTTPException(status_code=400, detail="인증번호가 일치하지 않습니다.")

    user_db = db.query(UserTable).filter(UserTable.user_id == user_id).first()
    if user_db:
        raise HTTPException(status_code=400, detail="이미 해당 ID가 있습니다.")

    hashed = bcrypt.hashpw(raw_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    db.add(UserTable(user_id=user_id, password=hashed, email=user_email))
    db.delete(verification)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="이미 사용 중인 아이디 또는 이메일입니다.")
    return {"message": "회원가입 성공!"}


@router.post("/login")
def login_todo(login_data: LoginRequest, request: Request, db: Session = Depends(get_db)):
    login_data = login_data.model_dump()
    username = login_data.get('username')
    if not isinstance(username, str) or not username:
        raise HTTPException(400, '아이디를 입력해주세요.')
    auth_limit(request, username, 'login')
    user = db.query(UserTable).filter(UserTable.user_id == login_data.get("username")).first()
    if not user:
        raise HTTPException(status_code=404, detail="ID가 맞지 않습니다.")

    if bcrypt.checkpw(login_data.get("password").encode("utf-8"), user.password.encode("utf-8")):
        payload = {
            "sub": user.user_id,
            "ver": password_version(user.password),
            "exp": datetime.now(timezone.utc) + timedelta(days=7),
        }
        token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
        return {"access_token": token}
    raise HTTPException(status_code=401, detail="비밀번호가 맞지 않습니다.")


@router.post("/request-reset-code")
def request_reset_code(email_data: EmailRequest, request: Request, db: Session = Depends(get_db)):
    email_data = email_data.model_dump()
    user_email = email_data.get("email")
    if not isinstance(user_email, str) or not user_email:
        raise HTTPException(status_code=400, detail="이메일을 입력해주세요.")

    auth_limit(request, user_email, 'send')
    user = db.query(UserTable).filter(UserTable.email == user_email).first()
    if not user:
        raise HTTPException(status_code=400, detail="회원가입이 필요합니다.")

    code = str(secrets.randbelow(900000) + 100000)
    expire_time = datetime.now(KST).replace(tzinfo=None) + timedelta(minutes=3)
    db.query(EmailVerificationTable).filter(EmailVerificationTable.email == user_email,
                                           EmailVerificationTable.purpose == 'reset').delete()
    db.add(EmailVerificationTable(email=user_email, purpose='reset', code=code, expires_at=expire_time))
    db.commit()
    send_email(
        to=user_email,
        subject="투두리스트 비밀번호 재설정 인증번호입니다.",
        body=f"요청하신 인증번호는 [{code}] 입니다. 3분 내에 입력해주세요.",
    )
    return {"message": "인증번호가 발송되었습니다."}


@router.post("/reset-password")
def reset_password(reset_data: ResetPasswordRequest, request: Request, db: Session = Depends(get_db)):
    reset_data = reset_data.model_dump()
    email = reset_data.get('email')
    if not isinstance(email, str) or not email:
        raise HTTPException(400, '이메일을 입력해주세요.')
    auth_limit(request, email, 'verify')
    user_data = db.query(UserTable).filter(UserTable.email == reset_data.get("email")).first()
    if not user_data:
        raise HTTPException(status_code=400, detail="일치하는 계정이 없습니다.")

    verification = db.query(EmailVerificationTable).filter(
        EmailVerificationTable.email == reset_data.get("email"),
        EmailVerificationTable.purpose == 'reset',
    ).first()
    if not verification:
        raise HTTPException(status_code=400, detail="인증번호 요청을 먼저 진행해주세요.")
    if datetime.now(KST).replace(tzinfo=None) > verification.expires_at:
        db.delete(verification)
        db.commit()
        raise HTTPException(status_code=400, detail="인증 시간이 만료되었습니다.")
    if verification.code != reset_data.get("code"):
        raise HTTPException(status_code=400, detail="인증번호가 일치하지 않습니다.")

    hashed = bcrypt.hashpw(reset_data.get("new_password").encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    user_data.password = hashed
    db.delete(verification)
    db.commit()
    return {"message": "비밀번호 변경이 완료되었습니다."}
