"""Web Push: what actually goes to the push service."""
import asyncio
import base64
import json
import os
import time

import pywebpush
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from app import push
from app.db import SessionLocal
from app.models import PushSubscription

from .conftest import make_user


class Sent:
    status_code = 201
    text = ""
    headers: dict = {}


def _browser_keys():
    key = ec.generate_private_key(ec.SECP256R1())
    raw = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    b64 = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=").decode()  # noqa: E731
    return b64(raw), b64(os.urandom(16))


def test_push_uses_rfc_vapid_and_a_timeout(monkeypatch):
    calls = []

    def fake_post(url, timeout=None, **kw):
        calls.append({"url": url, "timeout": timeout, "headers": kw["headers"]})
        return Sent()

    monkeypatch.setattr(pywebpush.requests, "post", fake_post)
    uid = make_user("member")
    p256dh, auth = _browser_keys()
    with SessionLocal() as db:
        push.ensure_keys(db)
        db.add(PushSubscription(user_id=uid, endpoint="https://web.push.apple.com/QGuQyavXutnMH",
                                p256dh=p256dh, auth=auth))
        db.commit()
        assert asyncio.run(push.send_to_users(db, [uid], "Porch camera", "Person seen")) == 1
    (call,) = calls
    assert call["timeout"] == 10
    scheme, params = call["headers"]["Authorization"].split(" ", 1)
    fields = dict(part.strip().split("=", 1) for part in params.split(","))
    assert scheme == "vapid" and set(fields) == {"t", "k"}
    claims = json.loads(base64.urlsafe_b64decode(fields["t"].split(".")[1] + "=="))
    assert claims["aud"] == "https://web.push.apple.com"            # Apple checks these
    assert 0 < claims["exp"] - time.time() <= 24 * 3600
    assert call["headers"]["content-encoding"] == "aes128gcm"
