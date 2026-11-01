"""Request helpers: public URL, cookie flags, signed values."""
import base64
import hashlib
import hmac
import json
import os

from fastapi import Request, Response
from sqlalchemy.orm import Session

from . import config, settings_store
from .security import SESSION_COOKIE, SESSION_DAYS


def is_https(request: Request) -> bool:
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    return proto == "https" or '"https"' in request.headers.get("cf-visitor", "")


def base_url(request: Request | None, db: Session) -> str:
    configured = settings_store.get(db, "general")["public_url"] or os.environ.get("HAWK_PUBLIC_URL", "")
    if configured:
        return configured.rstrip("/")
    if request is None:
        return ""
    host = request.headers.get("x-forwarded-host") or request.headers.get("host", "localhost")
    return f'{"https" if is_https(request) else "http"}://{host}'


def set_session_cookie(response: Response, request: Request, token: str, persistent: bool = True) -> None:
    """Persistent ("Remember me") cookies last 120 days; others end when the browser closes."""
    response.set_cookie(
        SESSION_COOKIE, token, max_age=SESSION_DAYS * 86400 if persistent else None, httponly=True,
        secure=is_https(request), samesite="lax", path="/",
    )


def sign(data: dict) -> str:
    raw = base64.urlsafe_b64encode(json.dumps(data).encode()).decode()
    sig = hmac.new(config.secret_key().encode(), raw.encode(), hashlib.sha256).hexdigest()
    return f"{raw}.{sig}"


def unsign(value: str | None) -> dict | None:
    if not value or "." not in value:
        return None
    raw, sig = value.rsplit(".", 1)
    good = hmac.new(config.secret_key().encode(), raw.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, good):
        return None
    try:
        return json.loads(base64.urlsafe_b64decode(raw))
    except ValueError:
        return None
