from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import Annotated
import bcrypt
from fastapi_mail import ConnectionConfig, FastMail, MessageSchema, MessageType
import random
import os
from dotenv import load_dotenv
from database import SessionLocal, TodoTable, UserTable, EmailVerificationTable, engine, Base
from datetime import datetime, timedelta
import jwt  # 💡 상단에 라이브러리 임포트 필요

SECRET_KEY = os.getenv("JWT_SECRET_KEY")
ALGORITHM = "HS256"
load_dotenv()

conf = ConnectionConfig(
    MAIL_USERNAME=os.getenv("MAIL_USERNAME"),
    MAIL_PASSWORD=os.getenv("MAIL_PASSWORD"),
    MAIL_FROM=os.getenv("MAIL_USERNAME"),
    MAIL_PORT=587,
    MAIL_SERVER="smtp.gmail.com",
    MAIL_STARTTLS=True,
    MAIL_SSL_TLS=False,
    USE_CREDENTIALS=True,
    VALIDATE_CERTS=True
)

# 임시 임시 임시! 원래는 DB나 Redis에 저장해야 하지만, 
# 일단 테스트용으로 메모리에 인증번호를 저장할 딕셔너리
# 구조: {"사용자이메일": "6자리번호"}
email_verification_store = {}

Base.metadata.create_all(bind=engine)
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5500", "http://localhost:5500", "*"],
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

@app.get("/todos")
def todos_get(authorization: Annotated[str | None, Header()] = None, db: Session = Depends(get_db)):
    try:
        decoded_payload = jwt.decode(authorization[7:], SECRET_KEY, algorithms=[ALGORITHM])
        user_id = decoded_payload.get("sub")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="토큰이 만료되었습니다.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")
    
    todos = db.query(TodoTable).filter(TodoTable.owner_id == user_id).all()
    return [{"id": t.id, "content": t.todo} for t in todos]

@app.post("/todos")
def create_todo(todo_data: dict, authorization: Annotated[str | None, Header()] = None, db: Session = Depends(get_db)):
    content_from_front = todo_data.get("content")
    try:
        decoded_payload = jwt.decode(authorization[7:], SECRET_KEY, algorithms=[ALGORITHM])
        user_id = decoded_payload.get("sub")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="토큰이 만료되었습니다.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")

    new_todo = TodoTable(todo=content_from_front, owner_id=user_id)
    
    db.add(new_todo)
    db.commit()
    db.refresh(new_todo)
    
    return {"id": new_todo.id, "content": new_todo.todo}

@app.delete("/todos/{id}")
def delete_todo(id: int, authorization: Annotated[str | None, Header()] = None, db: Session = Depends(get_db)): # 💡 id: int 콜론 수정
    todo_to_delete = db.query(TodoTable).filter(TodoTable.id == id).first()
    try:
        decoded_payload = jwt.decode(authorization[7:], SECRET_KEY, algorithms=[ALGORITHM])
        user_id = decoded_payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="인증 정보가 올바르지 않습니다.")

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="토큰이 만료되었습니다.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")
    if not todo_to_delete:
        raise HTTPException(status_code=404, detail="해당 투두를 찾을 수 없습니다.")
    
    if user_id != todo_to_delete.owner_id:
        raise HTTPException(status_code=400, detail="본인 것만 삭제할 수 있습니다.")
    db.delete(todo_to_delete)
    db.commit()
    
    return {"message": "삭제 완료"}

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
        raise HTTPException(status_code=400, detail="인증 시간이 만료되었습니다. 다시 요청해주세요.")
        
    if verification.code != input_code:
        raise HTTPException(status_code=400, detail="인증번호가 일치하지 않습니다.")

    user_db = db.query(UserTable).filter(UserTable.user_id == user_id).first()
    if user_db:
        raise HTTPException(status_code=400, detail="이미 해당 ID가 있습니다.")

    password_bytes = raw_password.encode('utf-8')
    hashed_bytes = bcrypt.hashpw(password_bytes, bcrypt.gensalt())
    hashed_password = hashed_bytes.decode('utf-8')
    
    new_user = UserTable(
        user_id=user_id, 
        password=hashed_password, 
        email=user_email
    )
    db.add(new_user)
    
    db.delete(verification)
    
    db.commit()
    return {"message": "회원가입 성공!"}

@app.post("/login")
def login_todo(login_data: dict, db: Session = Depends(get_db)):
    user = db.query(UserTable).filter(UserTable.user_id == login_data.get("username")).first()

    if not user:
        raise HTTPException(status_code=404, detail="ID가 맞지 않습니다.")

    input_password_bytes = login_data.get("password").encode('utf-8')
    db_password_bytes = user.password.encode('utf-8')

    if bcrypt.checkpw(input_password_bytes, db_password_bytes):
        payload = {"sub": user.user_id}
        token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
        return { "access_token": token }
    raise HTTPException(status_code=404, detail="비밀번호가 맞지 않습니다.")

@app.post("/request-code")
async def request_verification_code(email_data: dict, db: Session = Depends(get_db)):
    user_email = email_data.get("email")
    if not user_email:
        raise HTTPException(status_code=400, detail="이메일을 입력해주세요.")
        
    code = str(random.randint(100000, 999999))
    
    expire_time = datetime.now() + timedelta(minutes=3)

    db.query(EmailVerificationTable).filter(EmailVerificationTable.email == user_email).delete()
    
    new_verification = EmailVerificationTable(email=user_email, code=code, expires_at=expire_time)
    db.add(new_verification)
    db.commit()
    
    message = MessageSchema(
        subject="투두리스트 회원가입 인증번호입니다.",
        recipients=[user_email],
        body=f"요청하신 인증번호는 [{code}] 입니다. 3분 내에 입력해주세요.",
        subtype=MessageType.plain
    )
    fm = FastMail(conf)
    await fm.send_message(message)
    
    return {"message": "인증번호가 발송되었습니다. 메일함을 확인하세요!"}

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
        raise HTTPException(status_code=400, detail="인증 시간이 만료되었습니다. 다시 요청해주세요.")
        
    if verification.code != reset_data.get("code"):
        raise HTTPException(status_code=400, detail="인증번호가 일치하지 않습니다.")


    password_bytes = reset_data.get("new_password").encode('utf-8')
    hashed_bytes = bcrypt.hashpw(password_bytes, bcrypt.gensalt())
    hashed_password = hashed_bytes.decode('utf-8')
    
    user_data.password = hashed_password
    db.delete(verification)
    db.commit()
    return {"message": "비밀번호 변경이 완료되었습니다."}

@app.post("/request-reset-code")
async def request_code(email_data: dict, db: Session = Depends(get_db)):
    user_email = email_data.get("email")
    if not user_email:
        raise HTTPException(status_code=400, detail="이메일을 입력해주세요.")
    user = db.query(UserTable).filter(UserTable.email == user_email).first()
    if not user:
        raise HTTPException(status_code=400, detail="회원가입이 필요합니다.")
    code = str(random.randint(100000, 999999))
    
    expire_time = datetime.now() + timedelta(minutes=3)

    db.query(EmailVerificationTable).filter(EmailVerificationTable.email == user_email).delete()
    
    new_verification = EmailVerificationTable(email=user_email, code=code, expires_at=expire_time)
    db.add(new_verification)
    db.commit()
    
    message = MessageSchema(
        subject="투두리스트 비밀번호 재설정 인증번호입니다.",
        recipients=[user_email],
        body=f"요청하신 인증번호는 [{code}] 입니다. 3분 내에 입력해주세요.",
        subtype=MessageType.plain
    )
    fm = FastMail(conf)
    await fm.send_message(message)

    return {"message": "인증번호가 발송되었습니다. 메일함을 확인하세요!"}