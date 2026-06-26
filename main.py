from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import Annotated
import bcrypt
import resend
import random, os
from dotenv import load_dotenv
from database import SessionLocal, TodoTable, UserTable, EmailVerificationTable, engine, Base
from datetime import datetime, timedelta, timezone
import jwt
import httpx
from apscheduler.schedulers.background import BackgroundScheduler

load_dotenv()

SECRET_KEY = os.getenv("JWT_SECRET_KEY")
ALGORITHM = "HS256"
KST = timezone(timedelta(hours=9))

resend.api_key = os.getenv("RESEND_API_KEY")
MAIL_FROM = os.getenv("MAIL_FROM")

Base.metadata.create_all(bind=engine)
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =====================
# 이메일 발송 유틸 (Resend)
# =====================
def send_email(to: str, subject: str, body: str):
    params = {
        "from": MAIL_FROM,
        "to": [to],
        "subject": subject,
        "text": body,
    }
    resend.Emails.send(params)


# =====================
# DB / 인증 유틸
# =====================
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user_id(authorization: Annotated[str | None, Header()] = None):
    try:
        decoded_payload = jwt.decode(authorization[7:], SECRET_KEY, algorithms=[ALGORITHM])
        user_id = decoded_payload.get("sub")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="토큰이 만료되었습니다.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")
    return user_id


# =====================
# 회원가입 / 로그인 / 비밀번호 재설정
# =====================
@app.post("/request-code")
def request_verification_code(email_data: dict, db: Session = Depends(get_db)):
    user_email = email_data.get("email")
    if not user_email:
        raise HTTPException(status_code=400, detail="이메일을 입력해주세요.")
    code = str(random.randint(100000, 999999))
    expire_time = datetime.now(KST).replace(tzinfo=None) + timedelta(minutes=3)
    db.query(EmailVerificationTable).filter(EmailVerificationTable.email == user_email).delete()
    db.add(EmailVerificationTable(email=user_email, code=code, expires_at=expire_time))
    db.commit()
    send_email(
        to=user_email,
        subject="투두리스트 회원가입 인증번호입니다.",
        body=f"요청하신 인증번호는 [{code}] 입니다. 3분 내에 입력해주세요."
    )
    return {"message": "인증번호가 발송되었습니다."}


@app.post("/signup")
def signup_todo(user_data: dict, db: Session = Depends(get_db)):
    user_id = user_data.get("username")
    raw_password = user_data.get("password")
    user_email = user_data.get("email")
    input_code = user_data.get("code")

    verification = db.query(EmailVerificationTable).filter(
        EmailVerificationTable.email == user_email
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
    db.commit()
    return {"message": "회원가입 성공!"}


@app.post("/login")
def login_todo(login_data: dict, db: Session = Depends(get_db)):
    user = db.query(UserTable).filter(UserTable.user_id == login_data.get("username")).first()
    if not user:
        raise HTTPException(status_code=404, detail="ID가 맞지 않습니다.")
    if bcrypt.checkpw(login_data.get("password").encode("utf-8"), user.password.encode("utf-8")):
        token = jwt.encode({"sub": user.user_id}, SECRET_KEY, algorithm=ALGORITHM)
        return {"access_token": token}
    raise HTTPException(status_code=404, detail="비밀번호가 맞지 않습니다.")


@app.post("/request-reset-code")
def request_reset_code(email_data: dict, db: Session = Depends(get_db)):
    user_email = email_data.get("email")
    if not user_email:
        raise HTTPException(status_code=400, detail="이메일을 입력해주세요.")
    user = db.query(UserTable).filter(UserTable.email == user_email).first()
    if not user:
        raise HTTPException(status_code=400, detail="회원가입이 필요합니다.")
    code = str(random.randint(100000, 999999))
    expire_time = datetime.now(KST).replace(tzinfo=None) + timedelta(minutes=3)
    db.query(EmailVerificationTable).filter(EmailVerificationTable.email == user_email).delete()
    db.add(EmailVerificationTable(email=user_email, code=code, expires_at=expire_time))
    db.commit()
    send_email(
        to=user_email,
        subject="투두리스트 비밀번호 재설정 인증번호입니다.",
        body=f"요청하신 인증번호는 [{code}] 입니다. 3분 내에 입력해주세요."
    )
    return {"message": "인증번호가 발송되었습니다."}


@app.post("/reset-password")
def reset_password(reset_data: dict, db: Session = Depends(get_db)):
    user_data = db.query(UserTable).filter(UserTable.email == reset_data.get("email")).first()
    if not user_data:
        raise HTTPException(status_code=400, detail="일치하는 계정이 없습니다.")
    verification = db.query(EmailVerificationTable).filter(
        EmailVerificationTable.email == reset_data.get("email")
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


# =====================
# 투두 CRUD
# =====================
@app.get("/todos")
def todos_get(authorization: Annotated[str | None, Header()] = None, db: Session = Depends(get_db)):
    user_id = get_current_user_id(authorization)
    todos = db.query(TodoTable).filter(TodoTable.owner_id == user_id).all()
    return [{
        "id": t.id,
        "content": t.todo,
        "completed": t.completed,
        "deadline": t.deadline.isoformat() if t.deadline else None
    } for t in todos]


@app.post("/todos")
def create_todo(todo_data: dict, authorization: Annotated[str | None, Header()] = None, db: Session = Depends(get_db)):
    content = todo_data.get("content")
    user_id = get_current_user_id(authorization)
    deadline_str = todo_data.get("deadline")
    deadline = datetime.fromisoformat(deadline_str) if deadline_str else None
    new_todo = TodoTable(todo=content, owner_id=user_id, deadline=deadline)
    db.add(new_todo)
    db.commit()
    db.refresh(new_todo)
    return {
        "id": new_todo.id,
        "content": new_todo.todo,
        "deadline": new_todo.deadline.isoformat() if new_todo.deadline else None
    }


@app.delete("/todos/{id}")
def delete_todo(id: int, authorization: Annotated[str | None, Header()] = None, db: Session = Depends(get_db)):
    user_id = get_current_user_id(authorization)
    todo = db.query(TodoTable).filter(TodoTable.id == id).first()
    if not todo:
        raise HTTPException(status_code=404, detail="해당 투두를 찾을 수 없습니다.")
    if user_id != todo.owner_id:
        raise HTTPException(status_code=400, detail="본인 것만 삭제할 수 있습니다.")
    db.delete(todo)
    db.commit()
    return {"message": "삭제 완료"}


@app.patch("/todos/{id}/toggle")
def toggle_todo(id: int, authorization: Annotated[str | None, Header()] = None, db: Session = Depends(get_db)):
    user_id = get_current_user_id(authorization)
    todo = db.query(TodoTable).filter(TodoTable.id == id).first()
    if not todo:
        raise HTTPException(status_code=404, detail="데이터가 없습니다.")
    if todo.owner_id != user_id:
        raise HTTPException(status_code=403, detail="본인 리스트가 아닙니다.")
    todo.completed = not todo.completed
    db.commit()
    return {"id": todo.id, "completed": todo.completed}


@app.patch("/todos/{id}/deadline")
def update_deadline(id: int, data: dict, authorization: Annotated[str | None, Header()] = None, db: Session = Depends(get_db)):
    user_id = get_current_user_id(authorization)
    todo = db.query(TodoTable).filter(TodoTable.id == id).first()
    if not todo:
        raise HTTPException(status_code=404, detail="데이터가 없습니다.")
    if todo.owner_id != user_id:
        raise HTTPException(status_code=403, detail="본인 리스트가 아닙니다.")
    deadline_str = data.get("deadline")
    todo.deadline = datetime.fromisoformat(deadline_str) if deadline_str else None
    todo.reminder_sent = False
    db.commit()
    return {
        "id": todo.id,
        "deadline": todo.deadline.isoformat() if todo.deadline else None
    }


# =====================
# 마감기한 리마인더 스케줄러 (30분마다 체크)
# =====================
def check_deadlines():
    db = SessionLocal()
    try:
        now = datetime.now(KST).replace(tzinfo=None)
        deadline_24h = now + timedelta(hours=24)
        todos = db.query(TodoTable).filter(
            TodoTable.deadline != None,
            TodoTable.deadline > now,
            TodoTable.deadline <= deadline_24h,
            TodoTable.completed == False,
            TodoTable.reminder_sent == False
        ).all()
        for todo in todos:
            user = db.query(UserTable).filter(UserTable.user_id == todo.owner_id).first()
            if user:
                deadline_str = todo.deadline.strftime("%Y년 %m월 %d일 %H:%M")
                try:
                    send_email(
                        to=user.email,
                        subject="⏰ 투두리스트 마감기한 알림",
                        body=f"안녕하세요!\n\n아래 투두의 마감기한이 24시간 이내로 다가왔습니다.\n\n📌 할 일: {todo.todo}\n⏰ 마감기한: {deadline_str}\n\n서비스에 접속하여 완료 처리해 주세요!"
                    )
                    todo.reminder_sent = True
                    print(f"✅ 리마인더 발송: {user.email} - {todo.todo}")
                except Exception as e:
                    print(f"❌ 이메일 발송 실패: {e}")
        db.commit()
    finally:
        db.close()


def keep_alive():
    try:
        httpx.get("https://todolist-ezpr.onrender.com")
        print("✅ Keep alive ping 성공")
    except:
        pass


scheduler = BackgroundScheduler(timezone="Asia/Seoul")
scheduler.add_job(check_deadlines, 'interval', minutes=30)
scheduler.add_job(keep_alive, 'interval', minutes=10)
scheduler.start()