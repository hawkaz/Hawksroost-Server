"""Radio: scanner status, recordings, keep, incidents. Admin: dongles and channels."""
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config, settings_store, state
from ..db import get_db
from ..deps import admin, member, viewer
from ..models import RadioChannel, RadioDevice, RadioIncident, RadioRecording, User
from ..services import radio_config, radio_files
from ..timeutil import LOCAL_TZ, iso

router = APIRouter(tags=["radio"])

SEED_CHANNELS = [  # docs/RADIO.md — verify on RadioReference before enabling
    ("Sheriff", "CCSO-1", 155.490, False),
    ("Sheriff", "CCSO-2 Dispatch", 155.835, False),
    ("Fire/EMS", "Highlands Dispatch", 154.175, False),
    ("Fire/EMS", "Pinewood Dispatch", 154.190, False),
    ("Fire/EMS", "Pinewood Ops", 154.235, False),
    ("Fire/EMS", "Ponderosa Dispatch", 154.430, False),
    ("Forest Service", "Coconino North", 171.425, True),
    ("Forest Service", "Coconino South", 172.300, True),
    ("Weather", "NOAA WXK76", 162.400, False),
]


def _chan(c: RadioChannel) -> dict:
    return {"id": c.id, "device_id": c.device_id, "group": c.group, "label": c.label, "freq_mhz": c.freq_mhz,
            "modulation": c.modulation, "squelch_snr": c.squelch_snr, "incident": c.incident,
            "enabled": c.enabled, "sort": c.sort}


def _rec(r: RadioRecording, groups: dict[int, str]) -> dict:
    return {"id": r.id, "channel_id": r.channel_id, "group": groups.get(r.channel_id), "label": r.label,
            "freq_mhz": r.freq_mhz, "started_at": iso(r.started_at), "duration_s": round(r.duration_s, 1),
            "size_bytes": r.size_bytes, "keep": r.keep, "incident_id": r.incident_id,
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
    }


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


@router.get("/api/radio/incidents")
def incidents(limit: int = 30, db: Session = Depends(get_db), _: User = Depends(viewer)):
    rows = db.scalars(select(RadioIncident).order_by(RadioIncident.started_at.desc()).limit(min(limit, 100))).all()
    return [{"id": i.id, "channel_id": i.channel_id, "label": i.label, "started_at": iso(i.started_at),
             "ended_at": iso(i.ended_at), "tx_count": i.tx_count} for i in rows]


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
    """Add the starter channel list (turned off) and a first dongle, if missing."""
    dev = db.scalar(select(RadioDevice).limit(1))
    if dev is None:
        dev = RadioDevice(name="Dongle 1")
        db.add(dev)
        db.flush()
    have = {round(f, 4) for (f,) in db.execute(select(RadioChannel.freq_mhz))}
    added = 0
    for i, (group, label, freq, incident) in enumerate(SEED_CHANNELS):
        if round(freq, 4) not in have:
            db.add(RadioChannel(device_id=dev.id, group=group, label=label, freq_mhz=freq,
                                incident=incident, enabled=False, sort=i))
            added += 1
    db.commit()
    return {"added": added}


@router.post("/api/admin/radio/apply", dependencies=[Depends(admin)])
def apply(db: Session = Depends(get_db)):
    """Write the recorder config. The recorder restarts by itself within a few seconds."""
    return radio_config.apply(db)


def _404():
    raise HTTPException(404, "Not found")
