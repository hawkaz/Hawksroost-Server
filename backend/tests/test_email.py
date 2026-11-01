"""Email goes through Brevo's API. The network is mocked; this checks what we send and how failures read."""
import json

import httpx

from app import mailer

from .conftest import login, make_user


def brevo(status=201, body=None):
    sent = []

    def handler(request: httpx.Request):
        sent.append(request)
        return httpx.Response(status, json=body if body is not None else {"messageId": "<1@relay>"})
    mailer.TRANSPORT = httpx.MockTransport(handler)
    return sent


def setup_email(client):
    login(client, "admin")
    r = client.put("/api/admin/settings/email", json={"api_key": "xkeysib-test", "from_email": "cabin@hawksroost.live"})
    assert r.status_code == 200


def test_test_email_uses_brevo_api(client):
    sent = brevo()
    try:
        setup_email(client)
        assert client.post("/api/admin/settings/email/test", json={"to": "chris@example.com"}).status_code == 200
        req = sent[0]
        assert str(req.url) == "https://api.brevo.com/v3/smtp/email"
        assert req.headers["api-key"] == "xkeysib-test"
        body = json.loads(req.content)
        assert body["sender"] == {"name": "Hawksroost", "email": "cabin@hawksroost.live"}
        assert body["to"] == [{"email": "chris@example.com"}]
        assert body["subject"] and body["textContent"] and body["htmlContent"].startswith("<html>")
    finally:
        mailer.TRANSPORT = None


def test_bad_key_reads_plainly(client):
    brevo(401, {"code": "unauthorized", "message": "Key not found"})
    try:
        setup_email(client)
        r = client.post("/api/admin/settings/email/test", json={"to": "chris@example.com"})
        assert r.status_code == 400 and r.json()["detail"] == "Brevo didn't accept the API key: Key not found."
    finally:
        mailer.TRANSPORT = None


def test_blocked_ip_reads_plainly_and_shows_on_health(client):
    brevo(401, {"code": "unauthorized", "message": "We have detected you are using an unrecognised IP address "
                "9.170.116.246. If you performed this action make sure to add the new IP address in this link: "
                "https://app.brevo.com/security/authorised_ips"})
    try:
        setup_email(client)
        r = client.post("/api/admin/settings/email/test", json={"to": "chris@example.com"})
        detail = r.json()["detail"]
        assert r.status_code == 400 and "blocked the cabin's internet address (9.170.116.246)" in detail
        assert "API key" not in detail
        item = next(i for i in client.get("/api/admin/health").json()["items"] if i["name"] == "Email")
        assert item["ok"] is False and "Authorised IPs" in item["detail"]
        brevo()   # allowed in Brevo; the next send works and health clears
        assert client.post("/api/admin/settings/email/test", json={"to": "chris@example.com"}).status_code == 200
        item = next(i for i in client.get("/api/admin/health").json()["items"] if i["name"] == "Email")
        assert item["ok"] is True
    finally:
        mailer.TRANSPORT = None


def test_not_set_up(client):
    login(client, "admin")
    r = client.post("/api/admin/settings/email/test", json={"to": "chris@example.com"})
    assert r.status_code == 400 and "API key" in r.json()["detail"]
    assert client.get("/api/auth/config").json()["email"] is False


def test_invite_still_works_when_email_fails(client):
    brevo(500, {"message": "Internal error"})
    try:
        setup_email(client)
        r = client.post("/api/admin/invites", json={"email": "pat@example.com", "send_email": True})
        assert r.status_code == 201 and r.json()["url"] and r.json()["emailed"] is False
    finally:
        mailer.TRANSPORT = None


def test_html_body_links_and_escapes():
    out = mailer._html("Hi <Pat>,\n\nLink: https://hawksroost.live/invite/abc\nThanks")
    assert "&lt;Pat&gt;" in out and '<a href="https://hawksroost.live/invite/abc">' in out and "<br>" in out


def test_reset_email_goes_out(client):
    sent = brevo()
    try:
        setup_email(client)
        make_user("member", "sam@example.com")
        assert client.post("/api/auth/forgot", json={"email": "sam@example.com"}).status_code == 202
        assert json.loads(sent[-1].content)["to"] == [{"email": "sam@example.com"}]
    finally:
        mailer.TRANSPORT = None
