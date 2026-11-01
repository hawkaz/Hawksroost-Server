"""Sign-in: email/password, Google, invites, password reset. No open registration."""
import logging
import secrets
from datetime import timedelta
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import config, mailer, push, settings_store, users
from ..db import get_db
from ..deps import client_ip, current_user, optional_user
from ..models import AccessRequest, Invite, PasswordReset, User
from ..security import (
    SESSION_COOKIE, create_session, end_session, hash_password, hash_token,
    RateLimiter, login_limiter, new_token, verify_password,
)
from ..timeutil import utcnow
from ..web import base_url, is_https, set_session_cookie, sign, unsign

log = logging.getLogger("hawk.auth")
router = APIRouter(prefix="/api/auth", tags=["auth"])
access_limiter = RateLimiter(limit=5, window_s=3600)

GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO = "https://openidconnect.googleapis.com/v1/userinfo"
OAUTH_COOKIE = "hr_oauth"
MIN_PASSWORD = 8


def _safe_next(value: str | None) -> str:
    return value if value and value.startswith("/") and not value.startswith("//") else "/"


@router.get("/config")
def auth_config(db: Session = Depends(get_db)):
    g = settings_store.get(db, "google")
    general = settings_store.get(db, "general")
    return {
        "site_name": general["site_name"],
        "login_photo": f"/api/auth/login-photo?v={general['login_photo_v']}" if general["login_photo"] else None,
        "google": bool(g["enabled"] and g["client_id"] and g["client_secret"]),
        "email": mailer.is_configured(db),
        "request_access": True,
    }


@router.get("/login-photo")
def login_photo(db: Session = Depends(get_db)):
    """Sign-in screen background, set by an admin. Public: it shows before anyone signs in."""
    ctype = settings_store.get(db, "general")["login_photo"]
    path = config.BRANDING_DIR / "login-photo"
    if not ctype or not path.exists():
        raise HTTPException(404)
    return FileResponse(path, media_type=ctype, headers={"Cache-Control": "public, max-age=86400"})


@router.get("/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return {**users.full(user), "push_public_key": push.public_key(db)}


@router.get("/check", status_code=204)
def check(user: User | None = Depends(optional_user)):
    """Used by nginx `auth_request` to guard video and radio streams."""
    if user is None:
        raise HTTPException(401)
    return Response(status_code=204)


class LoginIn(BaseModel):
    email: str
    password: str
    remember: bool = True


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    key = f"{client_ip(request)}|{body.email.lower()}"
    if not login_limiter.hit(key):
        raise HTTPException(429, "Too many tries. Wait 15 minutes and try again.")
    user = users.find_by_email(db, body.email)
    if user is None or not user.active or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "That email and password don't match.")
    token = create_session(db, user, request.headers.get("user-agent"), persistent=body.remember)
    set_session_cookie(response, request, token, persistent=body.remember)
    return users.full(user)


@router.post("/logout", status_code=204)
def logout(request: Request, db: Session = Depends(get_db)):
    end_session(db, request.cookies.get(SESSION_COOKIE))
    response = Response(status_code=204)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


# --- Invites -------------------------------------------------------------------

def _valid_invite(db: Session, token: str) -> Invite:
    inv = db.scalar(select(Invite).where(Invite.token_hash == hash_token(token)))
    if inv is None or inv.used_at or inv.expires_at < utcnow():
        raise HTTPException(404, "This invite link has expired or was already used. Ask for a new one.")
    return inv


@router.get("/invite/{token}")
def invite_info(token: str, db: Session = Depends(get_db)):
    inv = _valid_invite(db, token)
    return {"email": inv.email, "name": inv.name, "role": inv.role}


class AcceptIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    email: EmailStr
    password: str = Field(min_length=MIN_PASSWORD, max_length=200)


@router.post("/invite/{token}")
def accept_invite(token: str, body: AcceptIn, request: Request, response: Response, db: Session = Depends(get_db)):
    inv = _valid_invite(db, token)
    if users.find_by_email(db, body.email):
        raise HTTPException(409, "There's already an account with that email. Sign in instead.")
    user = users.create_user(db, body.name, body.email, inv.role, password_hash=hash_password(body.password))
    inv.used_at, inv.used_by = utcnow(), user.id
    db.commit()
    set_session_cookie(response, request, create_session(db, user, request.headers.get("user-agent")))
    return users.full(user)


# --- Google --------------------------------------------------------------------

def _google_cfg(db: Session) -> dict:
    g = settings_store.get(db, "google")
    if not (g["enabled"] and g["client_id"] and g["client_secret"]):
        raise HTTPException(404, "Google sign-in isn't set up.")
    return g


def google_redirect_uri(request: Request | None, db: Session) -> str:
    return f"{base_url(request, db)}/api/auth/google/callback"


@router.get("/google/start")
def google_start(request: Request, invite: str | None = None, next: str | None = None, remember: bool = True,
                 db: Session = Depends(get_db)):
    g = _google_cfg(db)
    state = secrets.token_urlsafe(16)
    params = {
        "client_id": g["client_id"], "redirect_uri": google_redirect_uri(request, db),
        "response_type": "code", "scope": "openid email profile", "state": state,
        "prompt": "select_account",
    }
    resp = RedirectResponse(f"{GOOGLE_AUTH}?{urlencode(params)}", status_code=302)
    resp.set_cookie(
        OAUTH_COOKIE, sign({"state": state, "invite": invite, "next": _safe_next(next), "remember": remember}),
        max_age=600, httponly=True, secure=is_https(request), samesite="lax", path="/api/auth",
    )
    return resp


def _fail(message: str) -> RedirectResponse:
    return RedirectResponse(f"/login?{urlencode({'error': message})}", status_code=302)


@router.get("/google/callback")
async def google_callback(request: Request, code: str | None = None, state: str | None = None, db: Session = Depends(get_db)):
    g = _google_cfg(db)
    saved = unsign(request.cookies.get(OAUTH_COOKIE))
    if not saved or not code or saved.get("state") != state:
        return _fail("Google sign-in timed out. Try again.")
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            tok = await client.post(GOOGLE_TOKEN, data={
                "code": code, "client_id": g["client_id"], "client_secret": g["client_secret"],
                "redirect_uri": google_redirect_uri(request, db), "grant_type": "authorization_code",
            })
            tok.raise_for_status()
            info = (await client.get(GOOGLE_USERINFO, headers={
                "Authorization": f"Bearer {tok.json()['access_token']}"})).json()
    except (httpx.HTTPError, KeyError, ValueError):
        log.exception("Google token exchange failed")
        return _fail("Google sign-in didn't work. Try again, or use your password.")

    sub, email = info.get("sub"), (info.get("email") or "").lower()
    if not sub or not email or not info.get("email_verified"):
        return _fail("Your Google account has no verified email.")

    user = db.scalar(select(User).where(User.google_sub == sub)) or users.find_by_email(db, email)
    if user is None and saved.get("invite"):
        try:
            inv = _valid_invite(db, saved["invite"])
        except HTTPException as e:
            return _fail(e.detail)
        user = users.create_user(db, info.get("name") or email.split("@")[0], email, inv.role, google_sub=sub)
        inv.used_at, inv.used_by = utcnow(), user.id
        db.commit()
    if user is None:
        return _fail("There's no account for that Google address. Ask for an invite.")
    if not user.active:
        return _fail("Your account is turned off. Ask an admin.")
    if not user.google_sub:
        user.google_sub = sub
        db.commit()

    resp = RedirectResponse(_safe_next(saved.get("next")), status_code=302)
    remember = bool(saved.get("remember", True))
    set_session_cookie(resp, request, create_session(db, user, request.headers.get("user-agent"), persistent=remember),
                       persistent=remember)
    resp.delete_cookie(OAUTH_COOKIE, path="/api/auth")
    return resp


# --- Password reset --------------------------------------------------------------

def make_reset_link(db: Session, request: Request | None, user: User) -> str:
    token = new_token()
    db.add(PasswordReset(token_hash=hash_token(token), user_id=user.id, expires_at=utcnow() + timedelta(days=2)))
    db.commit()
    return f"{base_url(request, db)}/reset/{token}"


class ForgotIn(BaseModel):
    email: str


@router.post("/forgot", status_code=202)
async def forgot(body: ForgotIn, request: Request, db: Session = Depends(get_db)):
    if not login_limiter.hit(f"forgot|{client_ip(request)}"):
        raise HTTPException(429, "Too many tries. Wait 15 minutes and try again.")
    user = users.find_by_email(db, body.email)
    if user is None or not user.active:
        return {"ok": True}  # same answer either way: don't reveal who has an account
    if mailer.is_configured(db):
        link = make_reset_link(db, request, user)
        site = settings_store.get(db, "general")["site_name"]
        try:
            await mailer.send(db, user.email, f"Reset your {site} password",
                              f"Hi {user.name},\n\nUse this link to set a new password (good for 2 days):\n{link}\n\n"
                              "If you didn't ask for this, ignore this email.")
            return {"ok": True}
        except Exception:
            log.exception("reset email failed")
    # No email set up (or it failed): ask the admins to send a reset link.
    await notify_admins(db, request, f"{user.name} forgot their password",
                        "Open People to send them a reset link.", "/admin/people")
    return {"ok": True}


# --- Request access ------------------------------------------------------------------

async def notify_admins(db: Session, request: Request | None, title: str, body: str, path: str) -> None:
    """Push to every admin; also email them when email is set up."""
    admins = db.scalars(select(User).where(User.role == "admin", User.active)).all()
    try:
        await push.send_to_users(db, [a.id for a in admins], title, body, url=path, tag="admin")
    except Exception:
        log.exception("admin push failed")
    if mailer.is_configured(db):
        link = f"{base_url(request, db)}{path}"
        for a in admins:
            try:
                await mailer.send(db, a.email, title, f"{body}\n\n{link}\n")
            except Exception:
                log.exception("admin email failed")


class AccessIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    email: EmailStr
    message: str | None = Field(None, max_length=1000)


@router.post("/request-access", status_code=202)
async def request_access(body: AccessIn, request: Request, db: Session = Depends(get_db)):
    if not access_limiter.hit(client_ip(request)):
        raise HTTPException(429, "Too many requests from here. Try again later.")
    email = str(body.email).lower()
    if users.find_by_email(db, email) is None:
        pending = db.scalar(select(AccessRequest).where(
            func.lower(AccessRequest.email) == email, AccessRequest.handled_at.is_(None)))
        if pending is None:
            db.add(AccessRequest(name=body.name.strip(), email=email, message=(body.message or "").strip() or None))
            db.commit()
            note = f"{body.name.strip()} ({email}) would like an account."
            if body.message:
                note += f' They wrote: "{body.message.strip()[:300]}"'
            await notify_admins(db, request, "Someone asked for access", note, "/admin/people")
    return {"ok": True}


def _valid_reset(db: Session, token: str) -> PasswordReset:
    r = db.scalar(select(PasswordReset).where(PasswordReset.token_hash == hash_token(token)))
    if r is None or r.used_at or r.expires_at < utcnow():
        raise HTTPException(404, "This reset link has expired or was already used.")
    return r


@router.get("/reset/{token}")
def reset_info(token: str, db: Session = Depends(get_db)):
    r = _valid_reset(db, token)
    return {"name": db.get(User, r.user_id).name}


class ResetIn(BaseModel):
    password: str = Field(min_length=MIN_PASSWORD, max_length=200)


@router.post("/reset/{token}")
def do_reset(token: str, body: ResetIn, request: Request, response: Response, db: Session = Depends(get_db)):
    r = _valid_reset(db, token)
    user = db.get(User, r.user_id)
    user.password_hash = hash_password(body.password)
    r.used_at = utcnow()
    db.commit()
    set_session_cookie(response, request, create_session(db, user, request.headers.get("user-agent")))
    return users.full(user)
