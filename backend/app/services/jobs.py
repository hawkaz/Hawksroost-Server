"""Daily housekeeping in the API process: backup, cleanup."""
import asyncio
import logging
import sqlite3
from datetime import datetime, timedelta

from sqlalchemy import delete

from .. import config, settings_store, state
from ..db import SessionLocal
from ..models import AuthSession, Invite, PasswordReset, StarlinkSample, WeatherEvent, WeatherObs
from ..timeutil import LOCAL_TZ, utcnow
from .cameras import cleanup_old_events

log = logging.getLogger("hawk.jobs")


def backup_now() -> dict:
    """Consistent copy of the SQLite database into data/backups, pruned to keep_days.

    Off-site copy: the `backup` container (rclone) syncs data/backups to OneDrive.
    """
    with SessionLocal() as db:
        cfg = settings_store.get(db, "backup")
    config.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    target = config.BACKUP_DIR / f"hawksroost-{datetime.now(LOCAL_TZ):%Y%m%d-%H%M}.db"
    src = sqlite3.connect(config.DB_PATH)
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    cutoff = datetime.now().timestamp() - int(cfg["keep_days"]) * 86400
    for old in config.BACKUP_DIR.glob("hawksroost-*.db"):
        if old.stat().st_mtime < cutoff:
            old.unlink()
    result = {"ok": True, "file": target.name, "detail": f"Saved {target.name} ({target.stat().st_size / 1e6:.1f} MB)"}
    with SessionLocal() as db:
        state.put(db, "backup", result)
    return result


def cleanup() -> None:
    now = utcnow()
    with SessionLocal() as db:
        db.execute(delete(AuthSession).where(AuthSession.expires_at < now))
        db.execute(delete(Invite).where(Invite.expires_at < now - timedelta(days=30)))
        db.execute(delete(PasswordReset).where(PasswordReset.expires_at < now - timedelta(days=7)))
        # Weather and Starlink detail: keep about two years.
        db.execute(delete(WeatherObs).where(WeatherObs.ts < now - timedelta(days=730)))
        db.execute(delete(WeatherEvent).where(WeatherEvent.ts < now - timedelta(days=730)))
        db.execute(delete(StarlinkSample).where(StarlinkSample.ts < now - timedelta(days=730)))
        db.commit()
    cleanup_old_events(days=30)


async def daily_loop() -> None:
    last_day = None
    while True:
        try:
            with SessionLocal() as db:
                cfg = settings_store.get(db, "backup")
            now = datetime.now(LOCAL_TZ)
            if now.date() != last_day and now.hour >= int(cfg["hour"]):
                last_day = now.date()
                await asyncio.to_thread(cleanup)
                if cfg["enabled"]:
                    await asyncio.to_thread(backup_now)
        except Exception as e:
            log.exception("daily job failed")
            with SessionLocal() as db:
                state.put(db, "backup", {"ok": False, "detail": f"Backup failed: {e}"})
        await asyncio.sleep(300)
