from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import Annotated
import bcrypt
import resend
import random, os
from dotenv import load_dotenv
from database import SessionLocal, TodoTable, UserTable, EmailVerificationTable, SubtaskTable, engine, Base
from datetime import datetime, timedelta, timezone
import jwt
import httpx
import calendar
from apscheduler.schedulers.background import BackgroundScheduler

REPEAT_CYCLES = {"none", "daily", "weekly", "monthly"}


def todo_dict(t, subtasks=None):
    return {
        "id": t.id,
        "content": t.todo,
        "completed": t.completed,
        "deadline": t.deadline.isoformat() if t.deadline else None,
        "category": t.category,
        "repeat": t.repeat_cycle,
        "priority": t.priority,
        "detail": t.detail,
        "sort_order": t.sort_order,
        "subtasks": subtasks if subtasks is not None else [],
    }


def subtask_dict(s):
    return {"id": s.id, "content": s.content, "completed": s.completed}


from datetime import datetime, timedelta

def add_interval(current_deadline: datetime, repeat_cycle: dict):
    if not repeat_cycle:
        return None
    
    rtype = repeat_cycle.get("type")
    
    if rtype == "daily":
        return current_deadline + timedelta(days=1)
    elif rtype == "interval":
        days_to_add = int(repeat_cycle.get("value", 1))
        return current_deadline + timedelta(days=days_to_add)
    elif rtype == "weekly":
        target_days_str = repeat_cycle.get("days", [])
        if not target_days_str:
            return current_deadline + timedelta(days=7)
            
        day_map = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
        target_days = [day_map[d] for d in target_days_str if d in day_map]
        
        current_weekday = current_deadline.weekday()
        
        days_ahead_list = []
        for t_day in target_days:
            diff = (t_day - current_weekday) % 7
            if diff == 0:
                diff = 7
            days_ahead_list.append(diff)
            
        return current_deadline + timedelta(days=min(days_ahead_list))
        
    elif rtype == "monthly":
        return current_deadline + timedelta(days=30)
        
    return None

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
    allow_credentials=False,
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
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="인증 정보가 없습니다.")
    token = authorization[7:]
    try:
        decoded_payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
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
        payload = {
            "sub": user.user_id,
            "exp": datetime.now(timezone.utc) + timedelta(days=7),
        }
        token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
        return {"access_token": token}
    raise HTTPException(status_code=401, detail="비밀번호가 맞지 않습니다.")


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
    todos = db.query(TodoTable).filter(TodoTable.owner_id == user_id).order_by(
        TodoTable.sort_order.is_(None), TodoTable.sort_order, TodoTable.id
    ).all()
    todo_ids = [t.id for t in todos]
    subs_by_todo = {}
    if todo_ids:
        subs = db.query(SubtaskTable).filter(SubtaskTable.todo_id.in_(todo_ids)).order_by(SubtaskTable.id).all()
        for s in subs:
            subs_by_todo.setdefault(s.todo_id, []).append(subtask_dict(s))
    return [todo_dict(t, subs_by_todo.get(t.id, [])) for t in todos]


@app.post("/todos")
def create_todo(todo_data: dict, authorization: Annotated[str | None, Header()] = None, db: Session = Depends(get_db)):
    content = todo_data.get("content")
    user_id = get_current_user_id(authorization)
    deadline_str = todo_data.get("deadline")
    deadline = datetime.fromisoformat(deadline_str) if deadline_str else None
    category = (todo_data.get("category") or None)
    if category:
        category = category.strip()[:50] or None
    repeat = todo_data.get("repeat") or {"type": "none"}
    priority = todo_data.get("priority", 1)
    if priority not in (0, 1, 2):
        priority = 1
    detail = (todo_data.get("detail") or None)
    new_todo = TodoTable(
        todo=content, owner_id=user_id, deadline=deadline,
        category=category, repeat_cycle=repeat, priority=priority, detail=detail
    )
    db.add(new_todo)
    db.commit()
    db.refresh(new_todo)
    return todo_dict(new_todo)


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
    spawned = None
    # 반복 투두를 '완료'로 체크하면 다음 회차를 자동 생성
    if todo.completed and todo.repeat_cycle.get("type") != "none" and todo.deadline:
        next_deadline = add_interval(todo.deadline, todo.repeat_cycle)
        if next_deadline:
            spawned = TodoTable(
                todo=todo.todo, owner_id=todo.owner_id, deadline=next_deadline,
                category=todo.category, repeat_cycle=todo.repeat_cycle,
                priority=todo.priority, detail=todo.detail,
                completed=False, reminder_sent=False
            )
            db.add(spawned)
    db.commit()
    result = {"id": todo.id, "completed": todo.completed}
    if spawned:
        db.refresh(spawned)
        result["spawned"] = todo_dict(spawned)
    return result


@app.patch("/todos/{id}")
def update_todo(id: int, data: dict, authorization: Annotated[str | None, Header()] = None, db: Session = Depends(get_db)):
    user_id = get_current_user_id(authorization)
    todo = db.query(TodoTable).filter(TodoTable.id == id).first()
    if not todo:
        raise HTTPException(status_code=404, detail="데이터가 없습니다.")
    if todo.owner_id != user_id:
        raise HTTPException(status_code=403, detail="본인 리스트가 아닙니다.")
    if "content" in data:
        content = (data.get("content") or "").strip()
        if not content:
            raise HTTPException(status_code=400, detail="내용을 입력해주세요.")
        todo.todo = content
    if "category" in data:
        category = data.get("category")
        todo.category = (category.strip()[:50] or None) if category else None
    if "repeat" in data:
        todo.repeat_cycle = data.get("repeat") or {"type": "none"}
    if "priority" in data:
        p = data.get("priority")
        if p in (0, 1, 2):
            todo.priority = p
    if "detail" in data:
        detail = data.get("detail")
        todo.detail = (detail.strip() or None) if detail else None
    db.commit()
    return todo_dict(todo)


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


@app.post("/todos/reorder")
def reorder_todos(data: dict, authorization: Annotated[str | None, Header()] = None, db: Session = Depends(get_db)):
    user_id = get_current_user_id(authorization)
    order = data.get("order") or []
    todos = db.query(TodoTable).filter(TodoTable.owner_id == user_id).all()
    todo_map = {t.id: t for t in todos}
    for index, todo_id in enumerate(order):
        todo = todo_map.get(todo_id)
        if todo:
            todo.sort_order = index
    db.commit()
    return {"message": "순서가 저장되었습니다."}


# =====================
# 서브태스크 (체크리스트)
# =====================
def _get_owned_todo(id: int, user_id: str, db: Session):
    todo = db.query(TodoTable).filter(TodoTable.id == id).first()
    if not todo:
        raise HTTPException(status_code=404, detail="데이터가 없습니다.")
    if todo.owner_id != user_id:
        raise HTTPException(status_code=403, detail="본인 리스트가 아닙니다.")
    return todo


@app.post("/todos/{id}/subtasks")
def create_subtask(id: int, data: dict, authorization: Annotated[str | None, Header()] = None, db: Session = Depends(get_db)):
    user_id = get_current_user_id(authorization)
    _get_owned_todo(id, user_id, db)
    content = (data.get("content") or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="내용을 입력해주세요.")
    sub = SubtaskTable(todo_id=id, content=content, completed=False)
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return subtask_dict(sub)


@app.patch("/subtasks/{sid}")
def update_subtask(sid: int, data: dict, authorization: Annotated[str | None, Header()] = None, db: Session = Depends(get_db)):
    user_id = get_current_user_id(authorization)
    sub = db.query(SubtaskTable).filter(SubtaskTable.id == sid).first()
    if not sub:
        raise HTTPException(status_code=404, detail="데이터가 없습니다.")
    _get_owned_todo(sub.todo_id, user_id, db)
    if "completed" in data:
        sub.completed = bool(data.get("completed"))
    if "content" in data:
        content = (data.get("content") or "").strip()
        if content:
            sub.content = content
    db.commit()
    return subtask_dict(sub)


@app.delete("/subtasks/{sid}")
def delete_subtask(sid: int, authorization: Annotated[str | None, Header()] = None, db: Session = Depends(get_db)):
    user_id = get_current_user_id(authorization)
    sub = db.query(SubtaskTable).filter(SubtaskTable.id == sid).first()
    if not sub:
        raise HTTPException(status_code=404, detail="데이터가 없습니다.")
    _get_owned_todo(sub.todo_id, user_id, db)
    db.delete(sub)
    db.commit()
    return {"message": "삭제 완료"}


# =====================
# 계정 관리 (비밀번호 변경 / 탈퇴)
# =====================
@app.post("/change-password")
def change_password(data: dict, authorization: Annotated[str | None, Header()] = None, db: Session = Depends(get_db)):
    user_id = get_current_user_id(authorization)
    user = db.query(UserTable).filter(UserTable.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    current = (data.get("current_password") or "").encode("utf-8")
    if not bcrypt.checkpw(current, user.password.encode("utf-8")):
        raise HTTPException(status_code=400, detail="현재 비밀번호가 일치하지 않습니다.")
    new_password = data.get("new_password") or ""
    if len(new_password) < 4:
        raise HTTPException(status_code=400, detail="새 비밀번호는 4자 이상이어야 합니다.")
    user.password = bcrypt.hashpw(new_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    db.commit()
    return {"message": "비밀번호가 변경되었습니다."}


@app.delete("/account")
def delete_account(data: dict, authorization: Annotated[str | None, Header()] = None, db: Session = Depends(get_db)):
    user_id = get_current_user_id(authorization)
    user = db.query(UserTable).filter(UserTable.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    password = (data.get("password") or "").encode("utf-8")
    if not bcrypt.checkpw(password, user.password.encode("utf-8")):
        raise HTTPException(status_code=400, detail="비밀번호가 일치하지 않습니다.")
    todo_ids = [t.id for t in db.query(TodoTable).filter(TodoTable.owner_id == user_id).all()]
    if todo_ids:
        db.query(SubtaskTable).filter(SubtaskTable.todo_id.in_(todo_ids)).delete(synchronize_session=False)
    db.query(TodoTable).filter(TodoTable.owner_id == user_id).delete(synchronize_session=False)
    db.query(EmailVerificationTable).filter(EmailVerificationTable.email == user.email).delete(synchronize_session=False)
    db.delete(user)
    db.commit()
    return {"message": "계정이 삭제되었습니다."}


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

@app.api_route("/health", methods=["GET", "HEAD"])
def health_check():
    return {"status": "ok"}


scheduler = BackgroundScheduler(timezone="Asia/Seoul")
scheduler.add_job(check_deadlines, 'interval', minutes=30)
scheduler.start()