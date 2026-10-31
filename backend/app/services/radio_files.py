"""Index the recorder's per-transmission MP3s, spot incidents, enforce retention.

RTLSDR-Airband writes `<template>_<YYYYMMDD>_<HHMMSS>_<freq>.mp3`, with a
`.tmp` suffix while the transmission is still going. Templates are `ch<id>`
(multichannel) or `dev<id>` (scan, channel found by frequency). [VERIFY the
exact frequency format on the real recorder; both Hz and MHz are accepted.]
"""
import asyncio
import logging
import re
from datetime import datetime, timedelta

from mutagen.mp3 import MP3
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import config, push, settings_store
from ..db import SessionLocal
from ..models import RadioChannel, RadioIncident, RadioRecording, User
from ..timeutil import utcnow

log = logging.getLogger("hawk.radio")

NAME_RE = re.compile(r"^(?P<tpl>(?:ch|dev)\d+)_(?P<d>\d{8})_(?P<t>\d{6})(?:_(?P<f>[\d.]+))?\.mp3(?P<tmp>\.tmp)?$")
SCAN_S = 3
RETENTION_EVERY_S = 600

active: dict[str, dict] = {}   # file name → info, for transmissions in progress


def parse_name(name: str) -> dict | None:
    m = NAME_RE.match(name)
    if not m:
        return None
    freq = None
    if m["f"]:
        f = float(m["f"])
        freq = f / 1e6 if f > 1e5 else (f / 1e3 if f > 1e3 else f)
    return {
        "template": m["tpl"],
        "started_at": datetime.strptime(m["d"] + m["t"], "%Y%m%d%H%M%S"),
        "freq_mhz": round(freq, 4) if freq else None,
        "in_progress": bool(m["tmp"]),
    }


def match_channel(db: Session, info: dict) -> RadioChannel | None:
    tpl = info["template"]
    if tpl.startswith("ch"):
        return db.get(RadioChannel, int(tpl[2:]))
    if info["freq_mhz"]:
        return db.scalar(select(RadioChannel).where(
            RadioChannel.device_id == int(tpl[3:]),
            func.abs(RadioChannel.freq_mhz - info["freq_mhz"]) < 0.0026))
    return None


def _duration(path) -> float:
    try:
        return float(MP3(path).info.length)
    except Exception:
        return 0.0


def index_new_files(db: Session, known: set[str]) -> list[RadioRecording]:
    """Add finished files to the database. Returns the new rows."""
    new_rows = []
    now_active = {}
    for entry in config.RECORDINGS_DIR.iterdir():
        name = entry.name
        info = parse_name(name)
        if info is None:
            continue
        if info["in_progress"]:
            now_active[name] = info
            continue
        if name in known:
            continue
        known.add(name)
        if db.scalar(select(RadioRecording.id).where(RadioRecording.path == name)):
            continue
        ch = match_channel(db, info)
        rec = RadioRecording(
            channel_id=ch.id if ch else None, freq_mhz=info["freq_mhz"] or (ch.freq_mhz if ch else None),
            label=ch.label if ch else (f"{info['freq_mhz']:.4f} MHz" if info["freq_mhz"] else info["template"]),
            started_at=info["started_at"], duration_s=_duration(entry), size_bytes=entry.stat().st_size, path=name)
        db.add(rec)
        new_rows.append(rec)
    db.commit()
    active.clear()
    for name, info in now_active.items():
        ch = match_channel(db, info)
        active[name] = {"channel_id": ch.id if ch else None, "label": ch.label if ch else info["template"],
                        "group": ch.group if ch else None, "freq_mhz": info["freq_mhz"] or (ch.freq_mhz if ch else None),
                        "since": info["started_at"]}
    return new_rows


async def detect_incidents(db: Session, new_rows: list[RadioRecording]) -> None:
    cfg = settings_store.get(db, "radio")
    window = timedelta(minutes=int(cfg["incident_window_min"]))
    cooldown = timedelta(minutes=int(cfg["incident_cooldown_min"]))
    now = utcnow()

    # Close incidents that went quiet.
    for inc in db.scalars(select(RadioIncident).where(RadioIncident.ended_at.is_(None))):
        if now - inc.last_activity_at > cooldown:
            inc.ended_at = inc.last_activity_at

    for rec in new_rows:
        ch = db.get(RadioChannel, rec.channel_id) if rec.channel_id else None
        if ch is None or not ch.incident:
            continue
        open_inc = db.scalar(select(RadioIncident).where(
            RadioIncident.channel_id == ch.id, RadioIncident.ended_at.is_(None)))
        if open_inc:
            open_inc.last_activity_at, open_inc.tx_count = rec.started_at, open_inc.tx_count + 1
            rec.keep, rec.incident_id = True, open_inc.id
            continue
        recent = db.scalars(select(RadioRecording).where(
            RadioRecording.channel_id == ch.id, RadioRecording.started_at >= rec.started_at - window)).all()
        if len(recent) >= int(cfg["incident_tx_count"]):
            inc = RadioIncident(channel_id=ch.id, label=ch.label, started_at=min(r.started_at for r in recent),
                                last_activity_at=rec.started_at, tx_count=len(recent))
            db.add(inc)
            db.flush()
            for r in recent:
                r.keep, r.incident_id = True, inc.id
            ids = [u.id for u in db.scalars(select(User).where(User.active, User.notify_radio))
                   if not push.is_muted(u, now)]
            db.commit()
            try:
                await push.send_to_users(db, ids, f"{ch.label} is busy",
                                         f"{len(recent)} transmissions in {int(cfg['incident_window_min'])} minutes.",
                                         url=f"/radio?channel={ch.id}", tag=f"radio-{ch.id}")
            except Exception:
                log.exception("radio push failed")
    db.commit()


def enforce_retention(db: Session) -> int:
    cfg = settings_store.get(db, "radio")
    removed = 0
    cutoff = utcnow() - timedelta(days=int(cfg["max_age_days"]))
    old = db.scalars(select(RadioRecording).where(RadioRecording.keep.is_(False), RadioRecording.started_at < cutoff)).all()
    cap = float(cfg["max_storage_gb"]) * 1e9
    total = db.scalar(select(func.coalesce(func.sum(RadioRecording.size_bytes), 0))) or 0
    doomed = list(old)
    total -= sum(r.size_bytes for r in old)
    if total > cap:
        for r in db.scalars(select(RadioRecording).where(
                RadioRecording.keep.is_(False), RadioRecording.started_at >= cutoff).order_by(RadioRecording.started_at)):
            if total <= cap:
                break
            doomed.append(r)
            total -= r.size_bytes
    for r in doomed:
        (config.RECORDINGS_DIR / r.path).unlink(missing_ok=True)
        db.delete(r)
        removed += 1
    db.commit()
    return removed


async def run() -> None:
    known: set[str] = set()
    last_retention = 0.0
    loop = asyncio.get_running_loop()
    while True:
        try:
            with SessionLocal() as db:
                if settings_store.get(db, "radio")["enabled"] and config.RECORDINGS_DIR.exists():
                    new_rows = index_new_files(db, known)
                    await detect_incidents(db, new_rows)
                    if loop.time() - last_retention > RETENTION_EVERY_S:
                        last_retention = loop.time()
                        n = enforce_retention(db)
                        if n:
                            log.info("radio retention removed %s recordings", n)
                else:
                    active.clear()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("radio indexer error")
        await asyncio.sleep(SCAN_S)
