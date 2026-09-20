"""Deadline reminder job and scheduler setup."""

from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

from backend.config import KST
from backend.database import SessionLocal
from backend.models import TodoTable, UserTable
from backend.services.email import send_email


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
            TodoTable.reminder_sent == False,
        ).all()

        for todo in todos:
            user = db.query(UserTable).filter(UserTable.user_id == todo.owner_id).first()
            if user:
                deadline_str = todo.deadline.strftime("%Y년 %m월 %d일 %H:%M")
                try:
                    send_email(
                        to=user.email,
                        subject="⏰ 투두리스트 마감기한 알림",
                        body=(
                            "안녕하세요!\n\n아래 투두의 마감기한이 24시간 이내로 다가왔습니다."
                            f"\n\n📌 할 일: {todo.todo}\n⏰ 마감기한: {deadline_str}"
                            "\n\n서비스에 접속하여 완료 처리해 주세요!"
                        ),
                    )
                    todo.reminder_sent = True
                    print(f"✅ 리마인더 발송: {user.email} - {todo.todo}")
                except Exception as error:
                    print(f"❌ 이메일 발송 실패: {error}")
        db.commit()
    finally:
        db.close()


def create_deadline_scheduler():
    scheduler = BackgroundScheduler(timezone="Asia/Seoul")
    scheduler.add_job(check_deadlines, "interval", minutes=30)
    return scheduler
