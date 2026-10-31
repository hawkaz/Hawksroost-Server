"""Shared user helpers and serialization."""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import FAMILY_COLORS, User
from .security import PERMISSIONS, can, new_token
from .timeutil import iso


def find_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(func.lower(User.email) == email.strip().lower()))


def pick_color(db: Session) -> str:
    used = [c for (c,) in db.execute(select(User.color)).all()]
    for c in FAMILY_COLORS:
        if c not in used:
            return c
    return FAMILY_COLORS[len(used) % len(FAMILY_COLORS)]


def create_user(db: Session, name: str, email: str, role: str, **fields) -> User:
    user = User(
        name=name.strip(), email=email.strip().lower(), role=role,
        color=pick_color(db), ical_token=new_token(), **fields,
    )
    db.add(user)
    db.commit()
    return user


def brief(user: User | None) -> dict | None:
    if user is None:
        return None
    return {"id": user.id, "name": user.name, "color": user.color}


def full(user: User) -> dict:
    return {
        "id": user.id, "name": user.name, "email": user.email, "role": user.role,
        "color": user.color, "active": user.active,
        "has_password": bool(user.password_hash), "has_google": bool(user.google_sub),
        "mute_until": iso(user.mute_until),
        "notify_bookings": user.notify_bookings, "notify_radio": user.notify_radio,
        "created_at": iso(user.created_at), "last_seen_at": iso(user.last_seen_at),
        "can": {p: can(user, p) for p in PERMISSIONS},
    }
