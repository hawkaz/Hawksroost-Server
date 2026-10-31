"""Outgoing email over SMTP (Brevo by default). Configured in Settings → Email."""
import asyncio
import smtplib
import ssl
from email.message import EmailMessage

from sqlalchemy.orm import Session

from . import settings_store


class EmailNotConfigured(Exception):
    pass


def is_configured(db: Session) -> bool:
    s = settings_store.get(db, "email")
    return bool(s["enabled"] and s["host"] and s["from_email"])


def _send(cfg: dict, to: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["From"] = f'{cfg["from_name"]} <{cfg["from_email"]}>' if cfg["from_name"] else cfg["from_email"]
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    port = int(cfg["port"] or 587)
    context = ssl.create_default_context()
    if port == 465:
        server = smtplib.SMTP_SSL(cfg["host"], port, context=context, timeout=20)
    else:
        server = smtplib.SMTP(cfg["host"], port, timeout=20)
        server.starttls(context=context)
    with server:
        if cfg["username"]:
            server.login(cfg["username"], cfg["password"])
        server.send_message(msg)


async def send(db: Session, to: str, subject: str, body: str) -> None:
    if not is_configured(db):
        raise EmailNotConfigured()
    cfg = settings_store.get(db, "email")
    await asyncio.to_thread(_send, cfg, to, subject, body)
