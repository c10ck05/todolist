"""Persistent authentication throttles and password-bound sessions."""
import hashlib
import hmac
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from backend.config import JWT_SECRET_KEY
from backend.database import SessionLocal
from backend.models import AuthRateLimitTable


def password_version(password_hash):
    return hmac.new(JWT_SECRET_KEY.encode(), password_hash.encode(), hashlib.sha256).hexdigest()


def consume_limit(scope, identity, limit, seconds):
    key = hashlib.sha256(f'{scope}:{identity}'.encode()).hexdigest()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with SessionLocal() as db:
        # Atomic SQL increments work across processes; never reset a live window.
        db.execute(update(AuthRateLimitTable).where(
            AuthRateLimitTable.key == key, AuthRateLimitTable.expires_at <= now
        ).values(attempts=0, expires_at=now + timedelta(seconds=seconds)))
        row = db.get(AuthRateLimitTable, key)
        if row is None:
            try:
                with db.begin_nested():
                    db.add(AuthRateLimitTable(key=key, attempts=0,
                                             expires_at=now + timedelta(seconds=seconds)))
                    db.flush()
            except IntegrityError:
                pass  # Another worker initialized the same window.
        changed = db.execute(update(AuthRateLimitTable).where(
            AuthRateLimitTable.key == key, AuthRateLimitTable.attempts < limit
        ).values(attempts=AuthRateLimitTable.attempts + 1)).rowcount
        db.commit()
        if not changed:
            row = db.get(AuthRateLimitTable, key)
            retry = max(1, int((row.expires_at - now).total_seconds()) + 1)
            raise HTTPException(429, '요청 횟수를 초과했습니다. 잠시 후 다시 시도해주세요.',
                                headers={'Retry-After': str(retry)})


def auth_limit(request: Request, identity: str, action: str):
    ip = request.client.host if request.client else 'unknown'
    consume_limit(f'{action}:ip', ip, 30, 900)
    # Lowercase only for limiting, to prevent bypassing by email casing.
    consume_limit(f'{action}:account', identity.strip().casefold(),
                  {'send': 3, 'verify': 5, 'login': 10}[action], 900)
    if action == 'send':
        consume_limit('send:cooldown', identity.strip().casefold(), 1, 60)
