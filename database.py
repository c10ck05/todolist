import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy import JSON

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class TodoTable(Base):
    __tablename__ = "todolist"
    id = Column(Integer, primary_key=True, index=True)
    todo = Column(Text, nullable=False)
    owner_id = Column(String(50), nullable=False)
    completed = Column(Boolean, default=False, nullable=False)
    deadline = Column(DateTime, nullable=True)
    reminder_sent = Column(Boolean, default=False, nullable=False)
    category = Column(String(50), nullable=True)
    repeat_cycle = Column(JSON, default="none", nullable=False)
    priority = Column(Integer, default=1, nullable=False)  # 0=낮음, 1=보통, 2=높음
    detail = Column(Text, nullable=True)                   # 메모/상세
    sort_order = Column(Integer, nullable=True)            # 수동 정렬용 (2단계)


class UserTable(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(50), unique=True, nullable=False)
    password = Column(String(100), nullable=False)
    email = Column(String(100), unique=True, nullable=False)


class EmailVerificationTable(Base):
    __tablename__ = "email_verifications"
    email = Column(String(100), primary_key=True)
    code = Column(String(6), nullable=False)
    expires_at = Column(DateTime, nullable=False)


class SubtaskTable(Base):
    __tablename__ = "subtasks"
    id = Column(Integer, primary_key=True, index=True)
    todo_id = Column(Integer, nullable=False, index=True)
    content = Column(Text, nullable=False)
    completed = Column(Boolean, default=False, nullable=False)