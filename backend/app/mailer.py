"""Outgoing email through Brevo's transactional email API.

Configured in Admin → Sign-in & email: just a Brevo API key and the address to
send from (on a domain verified in Brevo). The sender's name is the app name.
API: POST https://api.brevo.com/v3/smtp/email, key in the `api-key` header;
`sender`, `to`, `subject` and `htmlContent` are required (no template used).
"""
import html
import re

import httpx
from sqlalchemy.orm import Session

from . import settings_store, state

BREVO_URL = "https://api.brevo.com/v3/smtp/email"
TRANSPORT: httpx.AsyncBaseTransport | None = None  # tests swap in a mock


class EmailNotConfigured(Exception):
    pass


class EmailFailed(Exception):
    """Brevo refused or couldn't be reached. The message is safe to show an admin."""


def is_configured(db: Session) -> bool:
    s = settings_store.get(db, "email")
    return bool(s["api_key"] and s["from_email"])


def _html(text: str) -> str:
    """Plain text → simple HTML: escaped, links clickable, line breaks kept."""
    out = html.escape(text)
    out = re.sub(r"(https?://[^\s<]+)", r'<a href="\1">\1</a>', out)
    return "<html><body><p>" + out.replace("\n\n", "</p><p>").replace("\n", "<br>") + "</p></body></html>"


async def send(db: Session, to: str, subject: str, body: str) -> None:
    if not is_configured(db):
        raise EmailNotConfigured()
    try:
        await _send(db, to, subject, body)
    except EmailFailed as e:
        state.put(db, "email_last", {"ok": False, "detail": str(e)})   # shown on the System page
        raise
    state.put(db, "email_last", {"ok": True})


async def _send(db: Session, to: str, subject: str, body: str) -> None:
    cfg = settings_store.get(db, "email")
    site = settings_store.get(db, "general")["site_name"] or "Hawksroost"
    payload = {
        "sender": {"name": site[:70], "email": cfg["from_email"]},
        "to": [{"email": to}],
        "subject": subject,
        "textContent": body,
        "htmlContent": _html(body),
    }
    headers = {"api-key": cfg["api_key"], "accept": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=20, transport=TRANSPORT) as c:
            r = await c.post(BREVO_URL, json=payload, headers=headers)
    except httpx.HTTPError as e:
        raise EmailFailed(f"Couldn't reach Brevo ({type(e).__name__}). Check the laptop's internet.") from e
    if r.status_code in (200, 201, 202):
        return
    try:
        detail = r.json().get("message") or r.text
    except ValueError:
        detail = r.text
    if "unrecognised ip" in detail.lower() or "authorised_ips" in detail.lower():
        ip = re.search(r"\d{1,3}(?:\.\d{1,3}){3}", detail)
        raise EmailFailed(
            f"Brevo blocked the cabin's internet address{f' ({ip.group(0)})' if ip else ''}. Allow it in Brevo: "
            "Settings → Security → Authorised IPs (Brevo also emails you a link to do it). "
            "The cabin's address can change, so this may come back.")
    if r.status_code == 401:
        hint = "" if cfg["api_key"].startswith("xkeysib-") else " It should start with xkeysib- (an SMTP key won't work)."
        raise EmailFailed(f"Brevo didn't accept the API key: {detail}.{hint}")
    raise EmailFailed(f"Brevo said no ({r.status_code}): {detail}")
