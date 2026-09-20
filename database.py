"""Backward-compatible imports for older scripts.

New backend code should import from ``backend.database`` and ``backend.models``.
"""

from backend.database import Base, SessionLocal, engine
from backend.models import EmailVerificationTable, SubtaskTable, TodoTable, UserTable


__all__ = [
    "Base",
    "SessionLocal",
    "engine",
    "TodoTable",
    "UserTable",
    "EmailVerificationTable",
    "SubtaskTable",
]
