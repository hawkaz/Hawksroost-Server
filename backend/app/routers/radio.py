"""Radio: scanner status, recordings, keep, incidents. Admin: dongles and channels."""
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import config, settings_store, state
from ..db import get_db
from ..deps import admin, member, viewer
from ..models import RadioChannel, RadioDevice, RadioIncident, RadioRecording, User
from ..services import radio_config, radio_files
from ..timeutil import LOCAL_TZ, iso, utcnow

router = APIRouter(tags=["radio"])

# Researched 2026-10-31 for Mormon Lake (sources in docs/RADIO.md). Analog only.
# (group, label, MHz, tone Hz or None, incident alerts, on by default)
SEED_CHANNELS = [
    ("Fire/EMS", "Mormon Lake FD dispatch", 155.6175, 162.2, True, True),
    ("Fire/EMS", "Fire mutual aid (VFIRE21)", 154.280, None, True, True),
    ("Fire/EMS", "Highlands FD dispatch", 154.175, 100.0, False, True),
    ("Fire/EMS", "Summit FD Ops 1", 154.385, None, False, True),
    ("Fire/EMS", "Pinewood FD dispatch", 154.190, 192.8, False, True),
    ("Fire/EMS", "Ponderosa FD dispatch", 155.295, None, False, True),
    ("Fire/EMS", "Summit FD Ops 2", 154.160, 91.5, False, False),
    ("Fire/EMS", "Summit FD SW Ops", 155.430, 127.3, False, False),
    ("Fire/EMS", "Pinewood FD ops", 154.235, 94.8, False, False),
    ("Fire/EMS", "Ponderosa FD tac", 154.430, None, False, False),
    ("Fire/EMS", "Blue Ridge FD 1", 154.205, 156.7, False, False),
    ("Fire/EMS", "Blue Ridge FD 2", 155.970, 156.7, False, False),
    ("Fire/EMS", "Blue Ridge FD 3", 154.145, 156.7, False, False),
    ("Fire/EMS", "Flagstaff FD alarm (may be P25 now)", 153.935, 100.0, False, False),
    ("Fire/EMS", "Guardian Medical tac (old listing)", 155.325, 131.8, False, False),
    ("Fire/EMS", "Guardian Medical rpt (old listing)", 155.790, 131.8, False, False),
    ("Sheriff", "CCSO 2C dispatch, Mormon Mtn", 155.0175, 114.8, False, True),
    ("Sheriff", "CCSO 2A dispatch, Flagstaff", 155.835, 114.8, False, True),
    ("Sheriff", "CCSO 2A, O'Leary Peak", 155.640, 114.8, False, False),
    ("Sheriff", "AZ DPS District 2", 460.025, 100.0, False, False),
    ("Forest Service", "Coconino NF South net", 172.300, None, True, True),
    ("Forest Service", "Coconino NF North net", 171.425, None, False, True),
    ("Forest Service", "Flagstaff dispatch TAC 1", 171.550, None, True, True),
    ("Forest Service", "Air-to-ground 1", 168.725, None, True, True),
    ("Forest Service", "Air-to-ground 2", 166.9625, None, True, False),
    ("Forest Service", "Air-to-ground 3", 168.6625, None, True, False),
    ("Forest Service", "TAC 2 (2016 listing)", 168.675, None, False, False),
    ("Forest Service", "TAC 3 (2016 listing)", 168.775, None, False, False),
    ("Forest Service", "Flight following", 168.650, None, False, False),
    ("Forest Service", "AZ Forestry (DFFM) Elden", 151.400, 123.0, False, False),
    ("Weather", "NOAA WXK76 Flagstaff", 162.400, None, False, False),
    ("Weather", "NOAA WWG41 Payson", 162.425, None, False, False),
]


def _chan(c: RadioChannel) -> dict:
    return {"id": c.id, "device_id": c.device_id, "group": c.group, "label": c.label, "freq_mhz": c.freq_mhz,
            "modulation": c.modulation, "squelch_snr": c.squelch_snr, "ctcss": c.ctcss, "incident": c.incident,
            "enabled": c.enabled, "sort": c.sort}


def _rec(r: RadioRecording, groups: dict[int, str]) -> dict:
    return {"id": r.id, "channel_id": r.channel_id, "group": groups.get(r.channel_id), "label": r.label,
            "freq_mhz": r.freq_mhz, "started_at": iso(r.started_at), "duration_s": round(r.duration_s, 1),
            "size_bytes": r.size_bytes, "keep": r.keep, "incident_id": r.incident_id, "parts": r.parts or 1,
            "url": f"/api/radio/recordings/{r.id}/audio"}


@router.get("/api/radio/status")
def status(db: Session = Depends(get_db), _: User = Depends(viewer)):
    cfg = settings_store.get(db, "radio")
    plan = state.get(db, "radio_plan") or {"devices": []}
    last = db.scalar(select(RadioRecording).order_by(RadioRecording.started_at.desc()).limit(1))
    open_inc = db.scalars(select(RadioIncident).where(RadioIncident.ended_at.is_(None))).all()
    return {
        "enabled": cfg["enabled"],
        "active": [{**a, "since": iso(a["since"])} for a in radio_files.active.values()],
        "live": [{"device_id": d["id"], "name": d["name"], "mode": d["mode"], "url": f"/radio/live/{d['mount']}"}
                 for d in plan["devices"] if d.get("mount") and d["mode"] != "off"],
        "last_recording_at": iso(last.started_at) if last else None,
        "incidents": [{"id": i.id, "label": i.label, "started_at": iso(i.started_at), "tx_count": i.tx_count}
                      for i in open_inc],
        "tune": _tune_out(radio_config.tune_state(db)),
        "scan_channels": db.scalar(select(func.count()).select_from(RadioChannel).where(RadioChannel.enabled)) or 0,
    }


def _tune_out(t: dict | None) -> dict | None:
    if not t:
        return None
    return {"freq_mhz": t["freq_mhz"], "modulation": t["modulation"], "by": t.get("by"),
            "until": t["until"] + "Z" if t.get("until") else None}


class TuneIn(BaseModel):
    mode: Literal["scan", "manual"]
    freq_mhz: float | None = Field(None, ge=radio_config.MIN_MHZ, le=radio_config.MAX_MHZ)
    modulation: Literal["nfm", "am"] = "nfm"
    minutes: int = Field(60, ge=0, le=24 * 60)   # back to scanning after this long; 0 = until changed


@router.put("/api/radio/tune")
def tune(body: TuneIn, db: Session = Depends(get_db), user: User = Depends(member)):
    """Listen to one frequency, or go back to scanning the channel list. The recorder
    restarts on the new settings within a few seconds."""
    if body.mode == "manual":
        if body.freq_mhz is None:
            raise HTTPException(422, "Enter a frequency in MHz.")
        dev = db.scalar(select(RadioDevice).where(RadioDevice.enabled).order_by(RadioDevice.id).limit(1))
        if dev is None:
            raise HTTPException(400, "There's no radio dongle set up yet.")
        until = utcnow() + timedelta(minutes=body.minutes) if body.minutes else None
        state.put(db, "radio_tune", {"device_id": dev.id, "freq_mhz": round(body.freq_mhz, 4),
                                     "modulation": body.modulation, "by": user.name,
                                     "until": until.isoformat(timespec="seconds") if until else None})
    else:
        state.put(db, "radio_tune", {})
    summary = radio_config.apply(db)
    return {"tune": _tune_out(radio_config.tune_state(db)), "errors": summary["errors"]}


@router.get("/api/radio/channels")
def channels(db: Session = Depends(get_db), _: User = Depends(viewer)):
    rows = db.scalars(select(RadioChannel).where(RadioChannel.enabled)
                      .order_by(RadioChannel.group, RadioChannel.sort, RadioChannel.freq_mhz)).all()
    return [_chan(c) for c in rows]


@router.get("/api/radio/recordings")
def recordings(channel_id: int | None = None, group: str | None = None, day: date | None = None,
               keep: bool | None = None, before: datetime | None = None, limit: int = 100,
               db: Session = Depends(get_db), _: User = Depends(viewer)):
    q = select(RadioRecording)
    if channel_id:
        q = q.where(RadioRecording.channel_id == channel_id)
    if group:
        ids = select(RadioChannel.id).where(RadioChannel.group == group)
        q = q.where(RadioRecording.channel_id.in_(ids))
    if day:
        s = datetime(day.year, day.month, day.day, tzinfo=LOCAL_TZ).astimezone(UTC).replace(tzinfo=None)
        q = q.where(RadioRecording.started_at >= s, RadioRecording.started_at < s + timedelta(days=1))
    if keep is not None:
        q = q.where(RadioRecording.keep.is_(keep))
    if before:
        q = q.where(RadioRecording.started_at < before.replace(tzinfo=None))
    rows = db.scalars(q.order_by(RadioRecording.started_at.desc()).limit(min(limit, 300))).all()
    groups = {c.id: c.group for c in db.scalars(select(RadioChannel))}
    return [_rec(r, groups) for r in rows]


@router.get("/api/radio/recordings/{rec_id}/audio")
def audio(rec_id: int, download: bool = False, db: Session = Depends(get_db), _: User = Depends(viewer)):
    r = db.get(RadioRecording, rec_id)
    if r is None:
        raise HTTPException(404, "That recording was cleaned up.")
    path = (config.RECORDINGS_DIR / r.path).resolve()
    if not path.is_relative_to(config.RECORDINGS_DIR.resolve()) or not path.exists():
        raise HTTPException(404, "That recording was cleaned up.")
    name = f"{r.label}-{r.started_at:%Y%m%d-%H%M%S}.mp3".replace(" ", "_").replace("/", "-")
    return FileResponse(path, media_type="audio/mpeg", filename=name if download else None,
                        content_disposition_type="attachment" if download else "inline")


class KeepIn(BaseModel):
    keep: bool


@router.put("/api/radio/recordings/{rec_id}/keep")
def set_keep(rec_id: int, body: KeepIn, db: Session = Depends(get_db), _: User = Depends(member)):
    r = db.get(RadioRecording, rec_id)
    if r is None:
        raise HTTPException(404)
    r.keep = body.keep
    db.commit()
    return {"keep": r.keep}


@router.delete("/api/radio/recordings/{rec_id}", status_code=204, dependencies=[Depends(admin)])
def delete_recording(rec_id: int, db: Session = Depends(get_db)):
    """Delete a call and its audio file (kept calls too: an admin asked for it)."""
    r = db.get(RadioRecording, rec_id)
    if r is None:
        return
    path = (config.RECORDINGS_DIR / r.path).resolve()
    if path.is_relative_to(config.RECORDINGS_DIR.resolve()):
        path.unlink(missing_ok=True)
    db.delete(r)
    db.commit()


# --- Admin ------------------------------------------------------------------------------

class DeviceIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    serial: str | None = Field(None, max_length=32)
    index: int = Field(0, ge=0, le=15)
    gain: float = Field(32.0, ge=0, le=50)
    correction: int = Field(0, ge=-200, le=200)
    mode: str = Field("auto", pattern="^(auto|scan|multichannel)$")
    centerfreq: float | None = Field(None, ge=24, le=1766)
    live_stream: bool = True
    enabled: bool = True


def _dev(d: RadioDevice) -> dict:
    return {"id": d.id, "name": d.name, "serial": d.serial, "index": d.index, "gain": d.gain,
            "correction": d.correction, "mode": d.mode, "centerfreq": d.centerfreq,
            "live_stream": d.live_stream, "enabled": d.enabled}


@router.get("/api/admin/radio", dependencies=[Depends(admin)])
def admin_radio(db: Session = Depends(get_db)):
    return {
        "devices": [_dev(d) for d in db.scalars(select(RadioDevice).order_by(RadioDevice.id))],
        "channels": [_chan(c) for c in db.scalars(select(RadioChannel).order_by(
            RadioChannel.group, RadioChannel.sort, RadioChannel.freq_mhz))],
        "plan": state.get(db, "radio_plan"),
    }


@router.post("/api/admin/radio/devices", status_code=201, dependencies=[Depends(admin)])
def add_device(body: DeviceIn, db: Session = Depends(get_db)):
    d = RadioDevice(**body.model_dump())
    d.serial = (d.serial or "").strip() or None
    db.add(d)
    db.commit()
    return _dev(d)


@router.put("/api/admin/radio/devices/{dev_id}", dependencies=[Depends(admin)])
def edit_device(dev_id: int, body: DeviceIn, db: Session = Depends(get_db)):
    d = db.get(RadioDevice, dev_id) or _404()
    for k, v in body.model_dump().items():
        setattr(d, k, v)
    d.serial = (d.serial or "").strip() or None
    db.commit()
    return _dev(d)


@router.delete("/api/admin/radio/devices/{dev_id}", status_code=204, dependencies=[Depends(admin)])
def delete_device(dev_id: int, db: Session = Depends(get_db)):
    db.delete(db.get(RadioDevice, dev_id) or _404())
    db.commit()


class ChannelIn(BaseModel):
    device_id: int | None = None
    group: str = Field(min_length=1, max_length=40)
    label: str = Field(min_length=1, max_length=80)
    freq_mhz: float = Field(ge=24, le=1766)
    modulation: str = Field("nfm", pattern="^(nfm|am)$")
    squelch_snr: float | None = Field(None, ge=0, le=40)
    ctcss: float | None = Field(None, gt=60, lt=260)
    incident: bool = False
    enabled: bool = True
    sort: int = 0


@router.post("/api/admin/radio/channels", status_code=201, dependencies=[Depends(admin)])
def add_channel(body: ChannelIn, db: Session = Depends(get_db)):
    c = RadioChannel(**body.model_dump())
    db.add(c)
    db.commit()
    return _chan(c)


@router.put("/api/admin/radio/channels/{ch_id}", dependencies=[Depends(admin)])
def edit_channel(ch_id: int, body: ChannelIn, db: Session = Depends(get_db)):
    c = db.get(RadioChannel, ch_id) or _404()
    for k, v in body.model_dump().items():
        setattr(c, k, v)
    db.commit()
    return _chan(c)


@router.delete("/api/admin/radio/channels/{ch_id}", status_code=204, dependencies=[Depends(admin)])
def delete_channel(ch_id: int, db: Session = Depends(get_db)):
    db.delete(db.get(RadioChannel, ch_id) or _404())
    db.commit()


@router.post("/api/admin/radio/seed", dependencies=[Depends(admin)])
def seed(db: Session = Depends(get_db)):
    """Add the researched Mormon Lake channel list and a first dongle, if missing.
    A core set starts on; the rest are there to turn on as wanted."""
    dev = db.scalar(select(RadioDevice).limit(1))
    if dev is None:
        dev = RadioDevice(name="Dongle 1")
        db.add(dev)
        db.flush()
    have = {round(f, 4) for (f,) in db.execute(select(RadioChannel.freq_mhz))}
    added = 0
    for i, (group, label, freq, tone, incident, enabled) in enumerate(SEED_CHANNELS):
        if round(freq, 4) not in have:
            db.add(RadioChannel(device_id=dev.id, group=group, label=label, freq_mhz=freq, ctcss=tone,
                                incident=incident, enabled=enabled, sort=i))
            added += 1
    db.commit()
    return {"added": added}


@router.post("/api/admin/radio/apply", dependencies=[Depends(admin)])
def apply(db: Session = Depends(get_db)):
    """Write the recorder config. The recorder restarts by itself within a few seconds."""
    return radio_config.apply(db)


def _404():
    raise HTTPException(404, "Not found")
