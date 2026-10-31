"""The signed-in person's own profile, devices, and notification settings."""
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import push, users
from ..db import get_db
from ..deps import current_user
from ..models import FAMILY_COLORS, AlertPref, Camera, PushSubscription, User
from ..security import hash_password, verify_password
from ..timeutil import iso, utcnow

router = APIRouter(prefix="/api/me", tags=["me"])


class ProfileIn(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=80)
    color: str | None = None
    notify_bookings: bool | None = None
    notify_radio: bool | None = None


@router.patch("")
def update_profile(body: ProfileIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if body.color is not None and body.color not in FAMILY_COLORS:
        raise HTTPException(400, "Unknown colour")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(user, field, value.strip() if isinstance(value, str) else value)
    db.commit()
    return users.full(user)


class PasswordIn(BaseModel):
    current: str | None = None
    new: str = Field(min_length=8, max_length=200)


@router.post("/password", status_code=204)
def change_password(body: PasswordIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if user.password_hash and not verify_password(body.current or "", user.password_hash):
        raise HTTPException(400, "Your current password isn't right.")
    user.password_hash = hash_password(body.new)
    db.commit()


class MuteIn(BaseModel):
    minutes: int | None = Field(None, ge=0, le=60 * 24 * 60)  # None/0 = unmute
    until: datetime | None = None


@router.post("/mute")
def mute(body: MuteIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if body.until:
        # Browser sends an ISO time with offset; store naive UTC.
        user.mute_until = body.until.astimezone(UTC).replace(tzinfo=None) if body.until.tzinfo else body.until
    elif body.minutes:
        user.mute_until = utcnow() + timedelta(minutes=body.minutes)
    else:
        user.mute_until = None
    db.commit()
    return {"mute_until": iso(user.mute_until)}


# --- Push devices ------------------------------------------------------------------

class SubscriptionIn(BaseModel):
    endpoint: str
    keys: dict[str, str]
    device_label: str | None = Field(None, max_length=120)


@router.post("/push", status_code=201)
def subscribe(body: SubscriptionIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if "p256dh" not in body.keys or "auth" not in body.keys:
        raise HTTPException(400, "Bad subscription")
    sub = db.scalar(select(PushSubscription).where(PushSubscription.endpoint == body.endpoint))
    if sub is None:
        sub = PushSubscription(endpoint=body.endpoint, user_id=user.id, p256dh="", auth="")
        db.add(sub)
    sub.user_id, sub.p256dh, sub.auth = user.id, body.keys["p256dh"], body.keys["auth"]
    sub.device_label, sub.fail_count = body.device_label, 0
    db.commit()
    return {"id": sub.id}


class EndpointIn(BaseModel):
    endpoint: str


@router.post("/push/remove", status_code=204)
def unsubscribe(body: EndpointIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    sub = db.scalar(select(PushSubscription).where(
        PushSubscription.endpoint == body.endpoint, PushSubscription.user_id == user.id))
    if sub:
        db.delete(sub)
        db.commit()


@router.get("/push")
def devices(user: User = Depends(current_user), db: Session = Depends(get_db)):
    subs = db.scalars(select(PushSubscription).where(PushSubscription.user_id == user.id)).all()
    return [{"id": s.id, "device_label": s.device_label, "created_at": iso(s.created_at),
             "last_ok_at": iso(s.last_ok_at)} for s in subs]


@router.post("/push/test")
async def test_push(user: User = Depends(current_user), db: Session = Depends(get_db)):
    sent = await push.send_to_users(db, [user.id], "Test from the cabin", "Notifications are working.", url="/settings", tag="test")
    if not sent:
        raise HTTPException(400, "No devices got it. Turn on notifications on this device first.")
    return {"sent": sent}


# --- Camera alert preferences --------------------------------------------------------

DETECTION_TYPES = ("person", "vehicle", "animal", "motion")


@router.get("/alerts")
def get_alerts(user: User = Depends(current_user), db: Session = Depends(get_db)):
    prefs = {p.camera_id: p for p in db.scalars(select(AlertPref).where(AlertPref.user_id == user.id))}
    out = []
    for cam in db.scalars(select(Camera).where(Camera.enabled).order_by(Camera.sort, Camera.id)):
        p = prefs.get(cam.id)
        out.append({
            "camera_id": cam.id, "camera_name": cam.name,
            "enabled": bool(p and p.enabled), "types": p.types if p else ["person", "vehicle"],
            "mute_until": iso(p.mute_until) if p else None,
        })
    return {"types": DETECTION_TYPES, "cameras": out, "mute_until": iso(user.mute_until)}


class AlertPrefIn(BaseModel):
    enabled: bool | None = None
    types: list[Literal["person", "vehicle", "animal", "motion"]] | None = None
    mute_minutes: int | None = Field(None, ge=0, le=60 * 24 * 60)


@router.put("/alerts/{camera_id}")
def set_alert(camera_id: int, body: AlertPrefIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if db.get(Camera, camera_id) is None:
        raise HTTPException(404, "No such camera")
    p = db.scalar(select(AlertPref).where(AlertPref.user_id == user.id, AlertPref.camera_id == camera_id))
    if p is None:
        p = AlertPref(user_id=user.id, camera_id=camera_id, enabled=False, types=["person", "vehicle"])
        db.add(p)
    if body.enabled is not None:
        p.enabled = body.enabled
    if body.types is not None:
        p.types = list(dict.fromkeys(body.types))
    if body.mute_minutes is not None:
        p.mute_until = utcnow() + timedelta(minutes=body.mute_minutes) if body.mute_minutes else None
    db.commit()
    return {"enabled": p.enabled, "types": p.types, "mute_until": iso(p.mute_until)}
