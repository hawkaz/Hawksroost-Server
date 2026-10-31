from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .db import get_db
from .models import User
from .security import SESSION_COOKIE, can, session_user


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = session_user(db, request.cookies.get(SESSION_COOKIE))
    if user is None:
        raise HTTPException(401, "Not signed in")
    return user


def optional_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    return session_user(db, request.cookies.get(SESSION_COOKIE))


def require(permission: str):
    def checker(user: User = Depends(current_user)) -> User:
        if not can(user, permission):
            raise HTTPException(403, "You don't have permission to do that")
        return user
    return checker


viewer = require("view")
member = require("edit")
camera_control = require("camera_control")
admin = require("admin")


def client_ip(request: Request) -> str:
    """The visitor's address. Caddy sets X-Forwarded-For (it ignores any value
    the visitor sent), so its first entry is the real client."""
    forwarded = request.headers.get("x-forwarded-for", "")
    return (
        forwarded.split(",")[0].strip()
        or request.headers.get("x-real-ip")
        or (request.client.host if request.client else "unknown")
    )
