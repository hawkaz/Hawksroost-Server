"""Server-side commands, run inside the api container:

    docker compose exec api python -m app.cli invite-admin
"""
import argparse
import os
from datetime import timedelta

from sqlalchemy import select

from . import settings_store
from .db import SessionLocal
from .models import Invite, User
from .security import hash_token, new_token
from .timeutil import utcnow


def _base(db) -> str:
    url = settings_store.get(db, "general")["public_url"] or os.environ.get("HAWK_PUBLIC_URL", "")
    return url.rstrip("/") or "http://localhost:8080"


def invite_admin() -> None:
    with SessionLocal() as db:
        token = new_token()
        db.add(Invite(token_hash=hash_token(token), role="admin", expires_at=utcnow() + timedelta(days=2)))
        db.commit()
        print("\nAdmin invite (good for 2 days). Open this on your phone or PC:\n")
        print(f"  {_base(db)}/invite/{token}\n")


def reset_link(email: str) -> None:
    from .routers.auth import make_reset_link
    from .users import find_by_email
    with SessionLocal() as db:
        user = find_by_email(db, email)
        if user is None:
            print(f"No account with email {email}")
            return
        print(f"\nPassword reset link for {user.name} (good for 2 days):\n\n  {make_reset_link(db, None, user)}\n")


def list_users() -> None:
    with SessionLocal() as db:
        for u in db.scalars(select(User).order_by(User.name)):
            print(f"{u.id:>3}  {u.role:<7} {'on ' if u.active else 'off'}  {u.name}  <{u.email}>")


def backup() -> None:
    from .services.jobs import backup_now
    print(backup_now()["detail"])


def main() -> None:
    p = argparse.ArgumentParser(prog="app.cli")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("invite-admin", help="Create a one-time link to set up an admin account")
    r = sub.add_parser("reset-link", help="Create a password reset link for someone")
    r.add_argument("email")
    sub.add_parser("list-users")
    sub.add_parser("backup", help="Back up the database now")
    args = p.parse_args()
    if args.cmd == "invite-admin":
        invite_admin()
    elif args.cmd == "reset-link":
        reset_link(args.email)
    elif args.cmd == "list-users":
        list_users()
    elif args.cmd == "backup":
        backup()


if __name__ == "__main__":
    main()
