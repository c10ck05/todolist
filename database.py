import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

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