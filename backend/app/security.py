"""Passwords, tokens, sessions, roles."""
import hashlib
import secrets
import time
from collections import defaultdict
from datetime import timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy.orm import Session

from .models import AuthSession, User
from .timeutil import utcnow

SESSION_COOKIE = "hr_session"
SESSION_DAYS = 120       # "Remember me": stay signed in, sliding on use
SHORT_SESSION_HOURS = 24  # without "Remember me": ends a day after last use (cookie ends with the browser)

_hasher = PasswordHasher()

# Role ladder. Higher includes everything below.
ROLE_RANK = {"viewer": 0, "member": 1, "admin": 2}

# What each permission needs. Kept in one place so the UI and API agree.
PERMISSIONS = {
    "view": "viewer",            # see everything, listen, watch, download
    "edit": "member",            # bookings, lists, keep radio clips
    "camera_control": "member",  # pan/tilt, presets, camera light
    "admin": "admin",            # settings, users, invites, auto-track, siren
}


def can(user: User, permission: str) -> bool:
    return ROLE_RANK.get(user.role, -1) >= ROLE_RANK[PERMISSIONS[permission]]


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _lifetime(persistent: bool) -> timedelta:
    return timedelta(days=SESSION_DAYS) if persistent else timedelta(hours=SHORT_SESSION_HOURS)


def create_session(db: Session, user: User, user_agent: str | None, persistent: bool = True) -> str:
    token = new_token()
    now = utcnow()
    db.add(AuthSession(
        id=hash_token(token), user_id=user.id, created_at=now, last_seen_at=now, persistent=persistent,
        expires_at=now + _lifetime(persistent), user_agent=(user_agent or "")[:255],
    ))
    user.last_seen_at = now
    db.commit()
    return token


def session_user(db: Session, token: str | None) -> User | None:
    if not token:
        return None
    sess = db.get(AuthSession, hash_token(token))
    now = utcnow()
    if sess is None or sess.expires_at < now or not sess.user.active:
        return None
    # Slide the expiry at most every few minutes to avoid a write per request.
    if (now - sess.last_seen_at) > timedelta(minutes=10):
        sess.last_seen_at = now
        sess.expires_at = now + _lifetime(sess.persistent)
        sess.user.last_seen_at = now
        db.commit()
    return sess.user


def end_session(db: Session, token: str | None) -> None:
    if token:
        sess = db.get(AuthSession, hash_token(token))
        if sess:
            db.delete(sess)
            db.commit()


class RateLimiter:
    """In-memory attempt counter. Good enough for one process and a family."""

    def __init__(self, limit: int, window_s: int):
        self.limit, self.window = limit, window_s
        self.hits: dict[str, list[float]] = defaultdict(list)

    def hit(self, key: str) -> bool:
        """Record an attempt; False when over the limit."""
        now = time.monotonic()
        recent = [t for t in self.hits[key] if now - t < self.window]
        recent.append(now)
        self.hits[key] = recent
        return len(recent) <= self.limit


login_limiter = RateLimiter(limit=10, window_s=900)
