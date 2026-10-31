"""Bootstrap settings: only what the app needs before it can read its database.

Everything else (cameras, Tempest, Starlink, email, Google sign-in, radio) is
configured by an admin in the web UI and stored in the `settings` table.
"""
import os
import secrets
from pathlib import Path

DATA_DIR = Path(os.environ.get("HAWK_DATA_DIR", "/data"))
DB_PATH = DATA_DIR / "hawksroost.db"
SNAPSHOT_DIR = DATA_DIR / "snapshots"
BACKUP_DIR = DATA_DIR / "backups"
RADIO_DIR = DATA_DIR / "radio"
RECORDINGS_DIR = Path(os.environ.get("HAWK_RECORDINGS_DIR", str(DATA_DIR / "radio" / "recordings")))
GO2RTC_URL = os.environ.get("HAWK_GO2RTC_URL", "http://go2rtc:1984")
TZ_NAME = os.environ.get("TZ", "America/Phoenix")
APP_VERSION = os.environ.get("HAWK_VERSION", "dev")


def ensure_dirs() -> None:
    for d in (DATA_DIR, SNAPSHOT_DIR, BACKUP_DIR, RADIO_DIR, RECORDINGS_DIR):
        d.mkdir(parents=True, exist_ok=True)


def secret_key() -> str:
    """App signing key, generated once and kept in the data folder."""
    path = DATA_DIR / "secret_key"
    if not path.exists():
        ensure_dirs()
        path.write_text(secrets.token_urlsafe(48))
        path.chmod(0o600)
    return path.read_text().strip()
