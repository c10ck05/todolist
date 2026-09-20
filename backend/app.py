"""FastAPI application assembly and lifecycle management."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import backend.models  # Registers all SQLAlchemy mappings before create_all().
from backend.database import Base, engine
from backend.routers import account, auth, health, subtasks, todos
from backend.services.reminders import create_deadline_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = create_deadline_scheduler()
    scheduler.start()
    try:
        yield
    finally:
        scheduler.shutdown()


def create_app():
    Base.metadata.create_all(bind=engine)
    application = FastAPI(lifespan=lifespan)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(auth.router)
    application.include_router(todos.router)
    application.include_router(subtasks.router)
    application.include_router(account.router)
    application.include_router(health.router)
    return application


app = create_app()
