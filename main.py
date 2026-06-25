from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import Annotated
import bcrypt
from fastapi_mail import ConnectionConfig, FastMail, MessageSchema, MessageType
import random, os, asyncio
from dotenv import load_dotenv
from database import SessionLocal, TodoTable, UserTable, EmailVerificationTable, engine, Base
from datetime import datetime, timedelta
import jwt
from apscheduler.schedulers.background import BackgroundScheduler

load_dotenv()
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
ALGORITHM = "HS256"

conf = ConnectionConfig(
    MAIL_USERNAME=os.getenv("MAIL_USERNAME"),
    MAIL_PASSWORD=os.getenv("MAIL_PASSWORD"),
    MAIL_FROM=os.getenv("MAIL_FROM"),
    MAIL_PORT=587,
    MAIL_SERVER="smtp.gmail.com",
    MAIL_STARTTLS=True,
    MAIL_SSL_TLS=False,
    USE_CREDENTIALS=True,
    VALIDATE_CERTS=True
)

Base.metadata.create_all(bind=engine)
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
        "deadline": t.deadline.isoformat() if t.deadline else None  # ✅ 마감기한 포함
    } for t in todos]

@app.post("/todos")
def create_todo(todo_data: dict, authorization: Annotated[str | None, Header()] = None, db: Session = Depends(get_db)):
    content = todo_data.get("content")
    user_id = get_current_user_id(authorization)
    
    # ✅ 마감기한 처리
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

# ✅ 마감기한 업데이트 엔드포인트
@app.patch("/todos/{id}/deadline")
def update_deadline(id: int, data: dict, authorization: Annotated[str | None, Header()] = None, db: Session = Depends(get_db)):
    user_id = get_current_user_id(authorization)
    todo = db.query(TodoTable).filter(TodoTable.id == id).first()
    if not todo:
        raise HTTPException(status_code=404, detail="데이터가 없습니다.")
    if todo.owner_id != user_id:
        raise HTTPException(status_code=403, detail="본인 리스트가 아닙니다.")
    
    deadline_str = data.get("deadline")  # None이면 마감기한 제거
    todo.deadline = datetime.fromisoformat(deadline_str) if deadline_str else None
    todo.reminder_sent = False  # ✅ 변경 시 리마인더 초기화
    db.commit()
    
    return {
        "id": todo.id,
        "deadline": todo.deadline.isoformat() if todo.deadline else None
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

# =====================
# ✅ 마감기한 리마인더 스케줄러 (30분마다 체크)
# =====================
def check_deadlines():
    """마감 24시간 전에 이메일 발송"""
    db = SessionLocal()
    try:
        now = datetime.now()
        deadline_24h = now + timedelta(hours=24)
        
        # 24시간 이내 마감, 미완료, 아직 리마인더 미발송 투두
        todos = db.query(TodoTable).filter(
            TodoTable.deadline != None,
            TodoTable.deadline > now,              # 아직 안 지남
            TodoTable.deadline <= deadline_24h,    # 24시간 이내
            TodoTable.completed == False,
            TodoTable.reminder_sent == False
        ).all()
        
        for todo in todos:
            user = db.query(UserTable).filter(UserTable.user_id == todo.owner_id).first()
            if user:
                deadline_str = todo.deadline.strftime("%Y년 %m월 %d일 %H:%M")
                
                async def send_mail(email, content, deadline_str):
                    message = MessageSchema(
                        subject="⏰ 투두리스트 마감기한 알림",
                        recipients=[email],
                        body=f"""안녕하세요!

아래 투두의 마감기한이 24시간 이내로 다가왔습니다.

📌 할 일: {content}
⏰ 마감기한: {deadline_str}

서비스에 접속하여 완료 처리해 주세요!""",
                        subtype=MessageType.plain,
                        from_email="admin@hyunjae.co.kr"
                    )
                    fm = FastMail(conf)
                    await fm.send_message(message)
                
                try:
                    asyncio.run(send_mail(user.email, todo.todo, deadline_str))
                    todo.reminder_sent = True
                    print(f"✅ 리마인더 발송: {user.email} - {todo.todo}")
                except Exception as e:
                    print(f"❌ 이메일 발송 실패: {e}")
        
        db.commit()
    finally:
        db.close()

# 스케줄러 시작
scheduler = BackgroundScheduler(timezone="Asia/Seoul")
scheduler.add_job(check_deadlines, 'interval', minutes=30, id='deadline_checker')
scheduler.start()

# =====================
# 회원가입 / 로그인 / 비밀번호 재설정
# =====================
@app.post("/signup")
def signup_todo(user_data: dict, db: Session = Depends(get_db)):
    user_id = user_data.get("username")
    raw_password = user_data.get("password")
    user_email = user_data.get("email")
    input_code = user_data.get("code")
    
    verification = db.query(EmailVerificationTable).filter(EmailVerificationTable.email == user_email).first()
    if not verification:
        raise HTTPException(status_code=400, detail="인증번호 요청을 먼저 진행해주세요.")
    if datetime.now() > verification.expires_at:
        db.delete(verification)
        db.commit()
        raise HTTPException(status_code=400, detail="인증 시간이 만료되었습니다.")
    if verification.code != input_code:
        raise HTTPException(status_code=400, detail="인증번호가 일치하지 않습니다.")
    
    user_db = db.query(UserTable).filter(UserTable.user_id == user_id).first()
    if user_db:
        raise HTTPException(status_code=400, detail="이미 해당 ID가 있습니다.")
    
    hashed = bcrypt.hashpw(raw_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    new_user = UserTable(user_id=user_id, password=hashed, email=user_email)
    db.add(new_user)
    db.delete(verification)
    db.commit()
    return {"message": "회원가입 성공!"}

@app.post("/login")
def login_todo(login_data: dict, db: Session = Depends(get_db)):
    user = db.query(UserTable).filter(UserTable.user_id == login_data.get("username")).first()
    if not user:
        raise HTTPException(status_code=404, detail="ID가 맞지 않습니다.")
    if bcrypt.checkpw(login_data.get("password").encode('utf-8'), user.password.encode('utf-8')):
        token = jwt.encode({"sub": user.user_id}, SECRET_KEY, algorithm=ALGORITHM)
        return {"access_token": token}
    raise HTTPException(status_code=404, detail="비밀번호가 맞지 않습니다.")

@app.post("/request-code")
async def request_verification_code(email_data: dict, db: Session = Depends(get_db)):
    user_email = email_data.get("email")
    if not user_email:
        raise HTTPException(status_code=400, detail="이메일을 입력해주세요.")
    code = str(random.randint(100000, 999999))
    expire_time = datetime.now() + timedelta(minutes=3)
    db.query(EmailVerificationTable).filter(EmailVerificationTable.email == user_email).delete()
    db.add(EmailVerificationTable(email=user_email, code=code, expires_at=expire_time))
    db.commit()
    message = MessageSchema(
        subject="투두리스트 회원가입 인증번호입니다.",
        recipients=[user_email],
        body=f"요청하신 인증번호는 [{code}] 입니다. 3분 내에 입력해주세요.",
        subtype=MessageType.plain,
        from_email="admin@hyunjae.co.kr"
    )
    await FastMail(conf).send_message(message)
    return {"message": "인증번호가 발송되었습니다."}

@app.post("/request-reset-code")
async def request_reset_code(email_data: dict, db: Session = Depends(get_db)):
    user_email = email_data.get("email")
    if not user_email:
        raise HTTPException(status_code=400, detail="이메일을 입력해주세요.")
    user = db.query(UserTable).filter(UserTable.email == user_email).first()
    if not user:
        raise HTTPException(status_code=400, detail="회원가입이 필요합니다.")
    code = str(random.randint(100000, 999999))
    expire_time = datetime.now() + timedelta(minutes=3)
    db.query(EmailVerificationTable).filter(EmailVerificationTable.email == user_email).delete()
    db.add(EmailVerificationTable(email=user_email, code=code, expires_at=expire_time))
    db.commit()
    message = MessageSchema(
        subject="투두리스트 비밀번호 재설정 인증번호입니다.",
        recipients=[user_email],
        body=f"요청하신 인증번호는 [{code}] 입니다. 3분 내에 입력해주세요.",
        subtype=MessageType.plain,
        from_email="admin@hyunjae.co.kr"
    )
    await FastMail(conf).send_message(message)
    return {"message": "인증번호가 발송되었습니다."}

@app.post("/reset-password")
def reset_password(reset_data: dict, db: Session = Depends(get_db)):
    user_data = db.query(UserTable).filter(UserTable.email == reset_data.get("email")).first()
    if not user_data:
        raise HTTPException(status_code=400, detail="일치하는 계정이 없습니다.")
    verification = db.query(EmailVerificationTable).filter(EmailVerificationTable.email == reset_data.get("email")).first()
    if not verification:
        raise HTTPException(status_code=400, detail="인증번호 요청을 먼저 진행해주세요.")
    if datetime.now() > verification.expires_at:
        db.delete(verification)
        db.commit()
        raise HTTPException(status_code=400, detail="인증 시간이 만료되었습니다.")
    if verification.code != reset_data.get("code"):
        raise HTTPException(status_code=400, detail="인증번호가 일치하지 않습니다.")
    hashed = bcrypt.hashpw(reset_data.get("new_password").encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    user_data.password = hashed
    db.delete(verification)
    db.commit()
    return {"message": "비밀번호 변경이 완료되었습니다."}