"""Database table mappings."""

from sqlalchemy import JSON, Boolean, Column, DateTime, Integer, String, Text

from backend.database import Base


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
    priority = Column(Integer, default=1, nullable=False)
    detail = Column(Text, nullable=True)
    sort_order = Column(Integer, nullable=True)


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
