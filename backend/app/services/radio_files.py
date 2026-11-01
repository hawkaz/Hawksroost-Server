"""Turn the recorder's per-transmission MP3s into calls, spot incidents, enforce retention.

RTLSDR-Airband writes one file per transmission,
`<template>_<YYYYMMDD>_<HHMMSS>_<freq>.mp3` (UTC; `.tmp` while still going).
Templates are `ch<id>` (multichannel) or `dev<id>` (scan, channel found by
frequency). The recorder has no "hang time" or minimum-length option
(checked in v5.2.0), so the app does it:

- Transmissions on the same channel less than `join_gap_s` apart become one
  call: the parts are joined into a single MP3 (no re-encoding) in `calls/`.
- A finished call shorter than `min_call_s` is deleted, not saved.
- A call is finished once its channel has been quiet for `join_gap_s`.
"""
import asyncio
import logging
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

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
CALLS = "calls"            # finished calls live in recordings/calls/
MAX_CALL_S = 15 * 60       # a busy channel still gets split into calls of at most this long

active: dict[str, dict] = {}   # file name → info, for transmissions in progress
_durations: dict[tuple[str, int], float] = {}   # (name, size) → seconds
_legacy: set[str] | None = None                 # files indexed one-per-transmission before calls existed


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


@dataclass
class Part:
    path: Path
    info: dict
    duration: float

    @property
    def start(self) -> datetime:
        return self.info["started_at"]

    @property
    def end(self) -> datetime:
        return self.start + timedelta(seconds=self.duration)


def _key(info: dict) -> tuple:
    return (info["template"], info["freq_mhz"])


def group_calls(parts: list[Part], gap_s: float) -> list[list[Part]]:
    """Split one channel's transmissions (sorted by start) into calls."""
    calls: list[list[Part]] = []
    for p in parts:
        cur = calls[-1] if calls else None
        if (cur and gap_s > 0 and (p.start - cur[-1].end).total_seconds() <= gap_s
                and (p.end - cur[0].start).total_seconds() <= MAX_CALL_S):
            cur.append(p)
        else:
            calls.append([p])
    return calls


def _join(parts: list[Part], out: Path) -> None:
    """Join MP3 parts without re-encoding. ffmpeg writes a correct length header;
    if it fails, plain byte-joining still plays (MP3 is a stream of frames)."""
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".part")
    if len(parts) == 1:
        shutil.move(parts[0].path, tmp)
    else:
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as lst:
            for p in parts:
                lst.write(f"file '{p.path.as_posix()}'\n")
        try:
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0",
                            "-i", lst.name, "-c", "copy", "-f", "mp3", str(tmp)], check=True, timeout=120)
        except Exception as e:
            log.warning("ffmpeg join failed (%s); joining bytes instead", e)
            with tmp.open("wb") as f:
                for p in parts:
                    f.write(p.path.read_bytes())
        finally:
            Path(lst.name).unlink(missing_ok=True)
        for p in parts:
            p.path.unlink(missing_ok=True)
    tmp.replace(out)


def process_files(db: Session, now: datetime | None = None) -> list[RadioRecording]:
    """Find finished calls among the recorder's files, save them, and return the new rows."""
    global _legacy
    now = now or utcnow()
    cfg = settings_store.get(db, "radio")
    gap = max(0, int(cfg["join_gap_s"]))
    min_len = max(0, int(cfg["min_call_s"]))
    if _legacy is None:
        _legacy = set(db.scalars(select(RadioRecording.path).where(~RadioRecording.path.like(f"{CALLS}/%"))))

    finished: dict[tuple, list[Part]] = {}
    in_progress: dict[tuple, list[datetime]] = {}
    now_active = {}
    for entry in config.RECORDINGS_DIR.iterdir():
        info = parse_name(entry.name)
        if info is None or entry.name in _legacy:
            continue
        if info["in_progress"]:
            now_active[entry.name] = info
            in_progress.setdefault(_key(info), []).append(info["started_at"])
            continue
        size = entry.stat().st_size
        dur = _durations.get((entry.name, size))
        if dur is None:
            dur = _durations[(entry.name, size)] = _duration(entry)
        finished.setdefault(_key(info), []).append(Part(entry, info, dur))

    new_rows = []
    for key, parts in finished.items():
        parts.sort(key=lambda p: p.start)
        for call in group_calls(parts, gap):
            end = call[-1].end
            if (now - end).total_seconds() <= gap:
                continue   # the channel may not be done yet
            if any(0 <= (t - end).total_seconds() <= gap + 1 for t in in_progress.get(key, [])):
                continue   # someone is answering right now
            total = sum(p.duration for p in call)
            if total < min_len:
                for p in call:
                    p.path.unlink(missing_ok=True)
                log.info("radio: dropped a %.1f s call on %s (under %s s)", total, key, min_len)
                continue
            first = call[0]
            rel = f"{CALLS}/{first.path.name}"
            try:
                _join(call, config.RECORDINGS_DIR / rel)
            except Exception:
                log.exception("radio: couldn't save call %s", rel)
                continue
            out = config.RECORDINGS_DIR / rel
            ch = match_channel(db, first.info)
            freq = first.info["freq_mhz"] or (ch.freq_mhz if ch else None)
            rec = RadioRecording(
                channel_id=ch.id if ch else None, freq_mhz=freq,
                label=ch.label if ch else (f"{freq:.4f} MHz" if freq else first.info["template"]),
                started_at=first.start, duration_s=_duration(out) or total, size_bytes=out.stat().st_size,
                path=rel, parts=len(call))
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
            open_inc.last_activity_at, open_inc.tx_count = rec.started_at, open_inc.tx_count + (rec.parts or 1)
            rec.keep, rec.incident_id = True, open_inc.id
            continue
        recent = db.scalars(select(RadioRecording).where(
            RadioRecording.channel_id == ch.id, RadioRecording.started_at >= rec.started_at - window)).all()
        tx = sum(r.parts or 1 for r in recent)   # transmissions, not calls
        if tx >= int(cfg["incident_tx_count"]):
            inc = RadioIncident(channel_id=ch.id, label=ch.label, started_at=min(r.started_at for r in recent),
                                last_activity_at=rec.started_at, tx_count=tx)
            db.add(inc)
            db.flush()
            for r in recent:
                r.keep, r.incident_id = True, inc.id
            ids = [u.id for u in db.scalars(select(User).where(User.active, User.notify_radio))
                   if not push.is_muted(u, now)]
            db.commit()
            try:
                await push.send_to_users(db, ids, f"{ch.label} is busy",
                                         f"{tx} transmissions in {int(cfg['incident_window_min'])} minutes.",
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


def _process_once() -> list[int]:
    """File work (reading, joining with ffmpeg) runs off the event loop."""
    with SessionLocal() as db:
        return [r.id for r in process_files(db)]


async def run() -> None:
    last_retention = 0.0
    loop = asyncio.get_running_loop()
    while True:
        try:
            with SessionLocal() as db:
                on = settings_store.get(db, "radio")["enabled"] and config.RECORDINGS_DIR.exists()
            if on:
                ids = await asyncio.to_thread(_process_once)
                with SessionLocal() as db:
                    await detect_incidents(db, [r for r in (db.get(RadioRecording, i) for i in ids) if r])
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
