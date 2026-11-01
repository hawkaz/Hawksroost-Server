"""Admin: people, invites, integration settings, health."""
import logging
import shutil
from datetime import timedelta

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .. import config, mailer, settings_store, state, users
from ..db import get_db
from ..deps import admin
from ..models import FAMILY_COLORS, ROLES, AccessRequest, AuthSession, Camera, Invite, RadioRecording, User
from ..security import hash_token, new_token
from ..timeutil import iso, utcnow
from ..web import base_url
from .auth import google_redirect_uri, make_reset_link

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(admin)])
log = logging.getLogger("hawk.admin")


# --- People --------------------------------------------------------------------------

@router.get("/users")
def list_users(db: Session = Depends(get_db)):
    return [users.full(u) for u in db.scalars(select(User).order_by(User.name))]


class UserPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=80)
    role: str | None = None
    color: str | None = None
    active: bool | None = None


def _admins_left(db: Session, excluding: int) -> int:
    return db.scalar(select(func.count()).select_from(User).where(
        User.role == "admin", User.active, User.id != excluding)) or 0


@router.patch("/users/{user_id}")
def update_user(user_id: int, body: UserPatch, db: Session = Depends(get_db), me: User = Depends(admin)):
    user = db.get(User, user_id) or _404()
    if body.role is not None and body.role not in ROLES:
        raise HTTPException(400, "Unknown role")
    if body.color is not None and body.color not in FAMILY_COLORS:
        raise HTTPException(400, "Unknown colour")
    demoting = (body.role and body.role != "admin") or body.active is False
    if user.role == "admin" and demoting and _admins_left(db, user.id) == 0:
        raise HTTPException(400, "There has to be at least one admin.")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(user, field, value)
    if body.active is False:
        db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    db.commit()
    return users.full(user)


@router.delete("/users/{user_id}", status_code=204)
def delete_user(user_id: int, db: Session = Depends(get_db)):
    user = db.get(User, user_id) or _404()
    if user.role == "admin" and _admins_left(db, user.id) == 0:
        raise HTTPException(400, "There has to be at least one admin.")
    db.delete(user)
    db.commit()


@router.post("/users/{user_id}/reset-link")
def reset_link(user_id: int, request: Request, db: Session = Depends(get_db)):
    user = db.get(User, user_id) or _404()
    return {"url": make_reset_link(db, request, user)}


@router.post("/users/{user_id}/sign-out", status_code=204)
def sign_out_everywhere(user_id: int, db: Session = Depends(get_db)):
    db.execute(delete(AuthSession).where(AuthSession.user_id == user_id))
    db.commit()


# --- Invites -------------------------------------------------------------------------

class InviteIn(BaseModel):
    name: str | None = Field(None, max_length=80)
    email: EmailStr | None = None
    role: str = "member"
    days: int = Field(7, ge=1, le=60)
    send_email: bool = False
    request_id: int | None = None  # answering an access request


def _invite_out(inv: Invite, url: str | None = None) -> dict:
    return {"id": inv.id, "name": inv.name, "email": inv.email, "role": inv.role,
            "created_at": iso(inv.created_at), "expires_at": iso(inv.expires_at),
            "used_at": iso(inv.used_at), "url": url}


@router.get("/invites")
def list_invites(db: Session = Depends(get_db)):
    rows = db.scalars(select(Invite).where(Invite.used_at.is_(None), Invite.expires_at > utcnow())
                      .order_by(Invite.created_at.desc()))
    return [_invite_out(i) for i in rows]


@router.post("/invites", status_code=201)
async def create_invite(body: InviteIn, request: Request, db: Session = Depends(get_db), me: User = Depends(admin)):
    if body.role not in ROLES:
        raise HTTPException(400, "Unknown role")
    if body.email and users.find_by_email(db, body.email):
        raise HTTPException(409, "That person already has an account.")
    token = new_token()
    inv = Invite(token_hash=hash_token(token), name=body.name, email=body.email, role=body.role,
                 created_by=me.id, expires_at=utcnow() + timedelta(days=body.days))
    db.add(inv)
    if body.request_id:
        req = db.get(AccessRequest, body.request_id)
        if req and req.handled_at is None:
            req.handled_at, req.outcome = utcnow(), "invited"
    db.commit()
    url = f"{base_url(request, db)}/invite/{token}"
    emailed = False
    if body.send_email and body.email:
        site = settings_store.get(db, "general")["site_name"]
        try:
            await mailer.send(db, body.email, f"You're invited to {site}",
                              f"Hi{(' ' + body.name) if body.name else ''},\n\n{me.name} invited you to {site}, "
                              f"the family cabin app.\n\nSet up your account here (good for {body.days} days):\n{url}\n")
            emailed = True
        except (mailer.EmailNotConfigured, mailer.EmailFailed) as e:
            log.warning("invite email not sent: %s", e)   # the link is still shown to the admin
    return {**_invite_out(inv, url), "emailed": emailed}


@router.delete("/invites/{invite_id}", status_code=204)
def revoke_invite(invite_id: int, db: Session = Depends(get_db)):
    inv = db.get(Invite, invite_id) or _404()
    db.delete(inv)
    db.commit()


# --- Access requests (from the sign-in page) -----------------------------------------

@router.get("/access-requests")
def access_requests(db: Session = Depends(get_db)):
    rows = db.scalars(select(AccessRequest).where(AccessRequest.handled_at.is_(None))
                      .order_by(AccessRequest.created_at.desc())).all()
    return [{"id": r.id, "name": r.name, "email": r.email, "message": r.message, "created_at": iso(r.created_at)}
            for r in rows]


@router.post("/access-requests/{req_id}/dismiss", status_code=204)
def dismiss_request(req_id: int, db: Session = Depends(get_db)):
    req = db.get(AccessRequest, req_id) or _404()
    req.handled_at, req.outcome = utcnow(), "dismissed"
    db.commit()


# --- Settings ------------------------------------------------------------------------

EDITABLE = [s for s in settings_store.SECTIONS if s not in settings_store.HIDDEN_SECTIONS]


@router.get("/settings")
def get_settings(request: Request, db: Session = Depends(get_db)):
    data = {s: settings_store.public(db, s) for s in EDITABLE}
    data["google"]["redirect_uri"] = google_redirect_uri(request, db)
    return data


@router.put("/settings/{section}")
def put_settings(section: str, body: dict, request: Request, db: Session = Depends(get_db)):
    if section not in EDITABLE:
        raise HTTPException(404, "Unknown section")
    body = {k: v for k, v in body.items() if not k.startswith("login_photo")}  # set via /login-photo
    try:
        settings_store.update(db, section, body)
    except (TypeError, ValueError):
        raise HTTPException(400, "Check the values and try again.")
    return get_settings(request, db)[section]


class TestEmailIn(BaseModel):
    to: EmailStr


@router.post("/settings/email/test")
async def test_email(body: TestEmailIn, db: Session = Depends(get_db)):
    try:
        await mailer.send(db, body.to, "Test email from the cabin app", "If you can read this, email works.")
    except mailer.EmailNotConfigured:
        raise HTTPException(400, "Enter the Brevo API key and the send-from address, and save, first.")
    except mailer.EmailFailed as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@router.post("/backup")
async def backup_now():
    import asyncio

    from ..services.jobs import backup_now as run_backup
    try:
        return await asyncio.to_thread(run_backup)
    except Exception as e:
        raise HTTPException(500, f"Backup failed: {e}")


@router.get("/tempest/devices")
def tempest_devices(db: Session = Depends(get_db)):
    """Tempest serial numbers heard on the network, to help fill in Settings."""
    return state.get(db, "tempest_devices") or {}


# --- Sign-in photo ------------------------------------------------------------------

PHOTO_TYPES = {b"\xff\xd8\xff": "image/jpeg", b"\x89PNG": "image/png", b"RIFF": "image/webp"}
MAX_PHOTO = 10 * 1024 * 1024


@router.put("/login-photo")
async def upload_login_photo(request: Request, db: Session = Depends(get_db)):
    """Raw image body (the browser resizes it first). JPEG, PNG or WebP."""
    data = await request.body()
    if len(data) > MAX_PHOTO:
        raise HTTPException(413, "That photo is too big. Try a smaller one (under 10 MB).")
    ctype = next((t for magic, t in PHOTO_TYPES.items() if data.startswith(magic)), None)
    if ctype is None or (ctype == "image/webp" and data[8:12] != b"WEBP"):
        raise HTTPException(400, "Use a JPEG, PNG or WebP photo.")
    config.BRANDING_DIR.mkdir(parents=True, exist_ok=True)
    (config.BRANDING_DIR / "login-photo").write_bytes(data)
    v = int(settings_store.get(db, "general")["login_photo_v"]) + 1
    settings_store.update(db, "general", {"login_photo": ctype, "login_photo_v": v})
    return {"url": f"/api/auth/login-photo?v={v}"}


@router.delete("/login-photo", status_code=204)
def remove_login_photo(db: Session = Depends(get_db)):
    (config.BRANDING_DIR / "login-photo").unlink(missing_ok=True)
    settings_store.update(db, "general", {"login_photo": ""})


# --- Health --------------------------------------------------------------------------

def _age_s(ts) -> float | None:
    return (utcnow() - ts).total_seconds() if ts else None


@router.get("/health")
async def health(db: Session = Depends(get_db)):
    items = []

    def add(name, ok, detail, last=None):
        items.append({"name": name, "ok": ok, "detail": detail, "last": iso(last)})

    usage = shutil.disk_usage(config.DATA_DIR)
    free_pct = usage.free / usage.total * 100
    add("Disk", free_pct > 10, f"{usage.free / 1e9:.0f} GB free of {usage.total / 1e9:.0f} GB ({free_pct:.0f}%)")

    hb = state.get_row(db, "collector")
    add("Collector", bool(hb and _age_s(hb.updated_at) < 120),
        "Running" if hb and _age_s(hb.updated_at) < 120 else "Not reporting — check the collector container",
        hb.updated_at if hb else None)

    if settings_store.get(db, "tempest")["enabled"]:
        t = state.get_row(db, "tempest_obs")
        fresh = bool(t and _age_s(t.updated_at) < 300)
        add("Tempest", fresh, "Receiving data" if fresh else "No packets in the last 5 minutes",
            t.updated_at if t else None)

    if settings_store.get(db, "starlink")["enabled"]:
        s = state.get_row(db, "starlink_status")
        fresh = bool(s and _age_s(s.updated_at) < 300 and not s.value.get("error"))
        detail = "Dish reachable" if fresh else (
            (s.value.get("error") or "No word from the dish in 5 minutes") if s else "No data yet")
        add("Starlink", fresh, detail,
            s.updated_at if s else None)

    for cam in db.scalars(select(Camera).where(Camera.enabled)):
        ok = bool(cam.last_ok_at and _age_s(cam.last_ok_at) < 600)
        add(f"Camera · {cam.name}", ok, "Online" if ok else (cam.last_error or "Not reached yet"), cam.last_ok_at)

    try:
        async with httpx.AsyncClient(timeout=3) as c:
            r = await c.get(f"{config.GO2RTC_URL}/api")
        add("Video server", r.status_code == 200, "Running")
    except httpx.HTTPError:
        add("Video server", False, "go2rtc isn't answering")

    if settings_store.get(db, "radio")["enabled"]:
        last = db.scalar(select(func.max(RadioRecording.started_at)))
        add("Radio recorder", last is not None, "Recording" if last else "No recordings yet", last)

    b = state.get_row(db, "backup")
    if settings_store.get(db, "backup")["enabled"]:
        ok = bool(b and _age_s(b.updated_at) < 36 * 3600 and b.value.get("ok"))
        add("Backup", ok, b.value.get("detail", "") if b else "No backup yet", b.updated_at if b else None)

    add("Email", mailer.is_configured(db), "Set up" if mailer.is_configured(db) else "Not set up (optional)")
    g = settings_store.get(db, "google")
    add("Google sign-in", bool(g["enabled"] and g["client_id"]), "Set up" if g["enabled"] else "Not set up (optional)")
    return {"version": config.APP_VERSION, "items": items}


def _404():
    raise HTTPException(404, "Not found")
