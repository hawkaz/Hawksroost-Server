"""Web Push (VAPID). Keys are generated on first start and stored in settings."""
import asyncio
import base64
import json
import logging
from datetime import datetime

from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid02
from pywebpush import WebPushException, webpush
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import settings_store
from .models import PushSubscription, User
from .timeutil import utcnow

log = logging.getLogger("hawk.push")


def ensure_keys(db: Session) -> None:
    cfg = settings_store.get(db, "push")
    if cfg["vapid_private_pem"] and cfg["vapid_public_key"]:
        return
    v = Vapid02()
    v.generate_keys()
    pem = v.private_pem().decode()
    raw = v.public_key.public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    pub = base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
    settings_store.update(db, "push", {"vapid_private_pem": pem, "vapid_public_key": pub})
    log.info("Generated VAPID keys for Web Push")


def public_key(db: Session) -> str:
    return settings_store.get(db, "push")["vapid_public_key"]


def _contact(db: Session) -> str:
    email = settings_store.get(db, "email")["from_email"]
    url = settings_store.get(db, "general")["public_url"]
    return f"mailto:{email}" if email else (url or "mailto:admin@example.invalid")


def is_muted(user: User, now: datetime | None = None) -> bool:
    return bool(user.mute_until and user.mute_until > (now or utcnow()))


def _send_one(sub: PushSubscription, payload: str, vapid: Vapid02, claims: dict) -> int | None:
    """Returns an HTTP status on failure, None on success."""
    try:
        webpush(
            {"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}},
            data=payload, vapid_private_key=vapid, vapid_claims=dict(claims), ttl=3600,
            timeout=10,   # a push service that doesn't answer mustn't hold up the alert to everyone else
        )
        return None
    except WebPushException as e:
        return e.response.status_code if e.response is not None else 0
    except Exception:  # network trouble etc.
        log.exception("push send failed")
        return 0


async def send_to_users(
    db: Session, user_ids: list[int], title: str, body: str,
    url: str = "/", tag: str | None = None, image: str | None = None,
) -> int:
    """Send a notification to every device of the given users. Returns devices reached."""
    if not user_ids:
        return 0
    cfg = settings_store.get(db, "push")
    if not cfg["vapid_private_pem"]:
        return 0
    # RFC 8292 VAPID ("Authorization: vapid t=…, k=…"), which every push service takes,
    # Apple's included. Same keys as before, so existing devices stay subscribed.
    vapid = Vapid02.from_pem(cfg["vapid_private_pem"].encode())
    claims = {"sub": _contact(db)}
    payload = json.dumps({"title": title, "body": body, "url": url, "tag": tag, "image": image})
    subs = db.scalars(select(PushSubscription).where(PushSubscription.user_id.in_(user_ids))).all()
    results = await asyncio.gather(*(asyncio.to_thread(_send_one, s, payload, vapid, claims) for s in subs))
    sent = 0
    for sub, status in zip(subs, results):
        if status is None:
            sub.last_ok_at, sub.fail_count = utcnow(), 0
            sent += 1
        elif status in (404, 410):  # subscription gone (app uninstalled, permission revoked)
            db.delete(sub)
        else:
            sub.fail_count += 1
            if sub.fail_count >= 10:
                db.delete(sub)
    db.commit()
    return sent
