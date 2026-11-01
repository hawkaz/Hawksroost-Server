from app.models import RadioChannel, RadioDevice
from app.services.radio_config import plan_device, render_airband
from app.services.radio_files import parse_name


def chans(*freqs):
    return [RadioChannel(id=i + 1, device_id=1, group="G", label=f"C{i}", freq_mhz=f, modulation="nfm",
                         incident=False, enabled=True) for i, f in enumerate(freqs)]


def test_auto_picks_multichannel_when_it_fits():
    dev = RadioDevice(id=1, name="D", mode="auto", gain=30, correction=0, index=0, live_stream=True)
    p = plan_device(dev, chans(155.49, 155.835))
    assert p.mode == "multichannel" and not p.errors
    assert abs(p.centerfreq - 155.49) > 0.02 and abs(p.centerfreq - 155.835) > 0.02


def test_auto_picks_scan_when_spread():
    dev = RadioDevice(id=1, name="D", mode="auto", gain=30, correction=0, index=0, live_stream=True)
    p = plan_device(dev, chans(154.175, 171.425))
    assert p.mode == "scan"
    text = render_airband([p], "pw")
    assert 'mode = "scan"' in text and "171.4250" in text and 'filename_template = "dev1"' in text


def test_forced_multichannel_too_wide_errors():
    dev = RadioDevice(id=1, name="D", mode="multichannel", gain=30, correction=0, index=0, live_stream=False)
    p = plan_device(dev, chans(154.175, 171.425))
    assert p.errors


def test_parse_names():
    a = parse_name("ch3_20260714_120501_155490000.mp3")
    assert a["template"] == "ch3" and a["freq_mhz"] == 155.49 and not a["in_progress"]
    b = parse_name("dev1_20260714_120501_171.425.mp3.tmp")
    assert b["in_progress"] and b["freq_mhz"] == 171.425
    assert parse_name("random.mp3") is None


def test_ctcss_rendering():
    dev = RadioDevice(id=1, name="D", mode="auto", gain=30, correction=0, index=0, live_stream=False)
    scan = chans(155.6175, 172.3)
    scan[0].ctcss = 162.2
    text = render_airband([plan_device(dev, scan)], "pw")
    assert "ctcss = (162.2, 0.0);" in text
    multi = chans(155.0175, 155.835)
    multi[1].ctcss = 114.8
    text = render_airband([plan_device(dev, multi)], "pw")
    assert text.count("ctcss = 114.8;") == 1


def test_seed_loads_core_scan(client):
    from .conftest import login
    login(client, "admin")
    assert client.post("/api/admin/radio/seed").json()["added"] > 20
    r = client.get("/api/admin/radio").json()
    on = [c for c in r["channels"] if c["enabled"]]
    assert any(c["label"].startswith("Mormon Lake FD") and c["incident"] and c["ctcss"] == 162.2 for c in on)
    client.put("/api/admin/settings/radio", json={"enabled": True})
    plan = client.post("/api/admin/radio/apply").json()
    assert not plan["errors"] and plan["devices"][0]["mode"] == "scan"


# --- Calls: transmissions joined into one recording; short ones dropped -----------------

import shutil as _shutil
import subprocess as _sp
from datetime import datetime as _dt, timedelta as _td

import pytest as _pytest

from app import config as _config
from app.services import radio_files as _rf

needs_ffmpeg = _pytest.mark.skipif(not _shutil.which("ffmpeg"), reason="ffmpeg not installed")


def _tx(tpl: str, start: _dt, seconds: float, freq: str = "154445000", tmp: bool = False) -> None:
    """Write a fake transmission the way the recorder names it."""
    name = f"{tpl}_{start:%Y%m%d_%H%M%S}_{freq}.mp3" + (".tmp" if tmp else "")
    _sp.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
             f"sine=frequency=800:duration={seconds}", "-ac", "1", "-ar", "22050", "-b:a", "32k", "-f", "mp3",
             str(_config.RECORDINGS_DIR / name)], check=True)


@_pytest.fixture
def recdir():
    d = _config.RECORDINGS_DIR
    if d.exists():
        _shutil.rmtree(d)
    d.mkdir(parents=True)
    _rf._legacy, _rf._durations = None, {}
    yield d


def _settings(min_s=3, gap_s=10):
    from app import settings_store
    from app.db import SessionLocal
    with SessionLocal() as db:
        settings_store.update(db, "radio", {"enabled": True, "min_call_s": min_s, "join_gap_s": gap_s})


@needs_ffmpeg
def test_conversation_becomes_one_call_and_blips_are_dropped(recdir):
    from app.db import SessionLocal
    from app.models import RadioRecording
    _settings(min_s=3, gap_s=10)
    t0 = _dt(2026, 7, 4, 18, 0, 0)
    _tx("ch1", t0, 2)                          # dispatch
    _tx("ch1", t0 + _td(seconds=5), 3)         # unit answers 3 s later
    _tx("ch1", t0 + _td(seconds=12), 1)        # "copy", 4 s later
    _tx("ch1", t0 + _td(seconds=90), 1)        # a lone 1 s blip much later: dropped
    _tx("ch2", t0 + _td(seconds=6), 4, freq="155160000")   # another channel: its own call
    with SessionLocal() as db:
        rows = _rf.process_files(db, now=t0 + _td(minutes=5))
        calls = sorted((r.label, r.parts, round(r.duration_s)) for r in rows)
        paths = [r.path for r in rows]
        assert len(db.scalars(__import__("sqlalchemy").select(RadioRecording)).all()) == 2
    assert calls == [("154.4450 MHz", 3, 6), ("155.1600 MHz", 1, 4)]
    assert all(p.startswith("calls/") and (recdir / p).exists() for p in paths)
    assert not [f for f in recdir.iterdir() if f.is_file()]   # parts and the blip are gone


@needs_ffmpeg
def test_call_waits_while_the_channel_might_answer(recdir):
    from app.db import SessionLocal
    _settings(min_s=0, gap_s=10)
    t0 = _dt(2026, 7, 4, 18, 0, 0)
    _tx("ch1", t0, 2)
    reply = t0 + _td(seconds=11)
    with SessionLocal() as db:
        assert _rf.process_files(db, now=t0 + _td(seconds=8)) == []      # only 6 s of quiet so far
        _tx("ch1", reply, 2, tmp=True)                                   # someone answers 9 s after...
        before = _rf.active
        assert _rf.process_files(db, now=t0 + _td(seconds=25)) == []     # ...and is still talking: wait
        assert [a["since"] for a in _rf.active.values()] == [reply]      # shown as on the air now
        assert before == {} and _rf.active is not before                 # replaced, never changed in place
        (recdir / f"ch1_{reply:%Y%m%d_%H%M%S}_154445000.mp3.tmp").unlink()
        _tx("ch1", reply, 2)                                             # the reply finishes
        rows = _rf.process_files(db, now=t0 + _td(seconds=30))
        assert [r.parts for r in rows] == [2]
        assert _rf.active == {}
        _rf.process_files(db, now=t0 + _td(seconds=40))
        assert _rf._durations == {}                                      # parts joined: nothing left to remember


@needs_ffmpeg
def test_gap_zero_keeps_every_transmission(recdir):
    from app.db import SessionLocal
    _settings(min_s=0, gap_s=0)
    t0 = _dt(2026, 7, 4, 18, 0, 0)
    _tx("ch1", t0, 2)
    _tx("ch1", t0 + _td(seconds=3), 2)
    with SessionLocal() as db:
        rows = _rf.process_files(db, now=t0 + _td(minutes=1))
        assert sorted(r.parts for r in rows) == [1, 1]


@needs_ffmpeg
def test_files_indexed_before_calls_are_left_alone(recdir):
    from app.db import SessionLocal
    from app.models import RadioRecording
    _settings(min_s=0, gap_s=10)
    t0 = _dt(2026, 7, 4, 18, 0, 0)
    _tx("ch1", t0, 2)
    name = f"ch1_{t0:%Y%m%d_%H%M%S}_154445000.mp3"
    with SessionLocal() as db:
        db.add(RadioRecording(label="old", started_at=t0, path=name))
        db.commit()
        assert _rf.process_files(db, now=t0 + _td(minutes=1)) == []
    assert (recdir / name).exists()


def test_only_admins_delete_calls(client, recdir):
    from app.db import SessionLocal
    from app.models import RadioRecording
    from .conftest import login
    (recdir / "calls").mkdir()
    f = recdir / "calls" / "ch1_20260704_180000_154445000.mp3"
    f.write_bytes(b"ID3")
    with SessionLocal() as db:
        r = RadioRecording(label="Fire", started_at=_dt(2026, 7, 4, 18), path="calls/" + f.name, keep=True, parts=3)
        db.add(r)
        db.commit()
        rid = r.id
    login(client, "member")
    assert client.get("/api/radio/recordings").json()[0]["parts"] == 3
    assert client.delete(f"/api/radio/recordings/{rid}").status_code == 403
    client.post("/api/auth/logout")
    login(client, "admin")
    assert client.delete(f"/api/radio/recordings/{rid}").status_code == 204
    assert not f.exists() and client.get("/api/radio/recordings").json() == []


# --- Manual tuning: one frequency instead of scanning ---------------------------------------

def test_manual_tuning_renders_one_frequency(client):
    from app import settings_store, state
    from app.db import SessionLocal
    from app.services import radio_config
    from .conftest import login
    login(client, "admin")
    assert client.post("/api/admin/radio/seed").status_code == 200
    with SessionLocal() as db:
        settings_store.update(db, "radio", {"enabled": True})
    client.post("/api/auth/logout")
    login(client, "viewer")
    assert client.put("/api/radio/tune", json={"mode": "manual", "freq_mhz": 155.16}).status_code == 403
    client.post("/api/auth/logout")
    login(client, "member")
    assert client.put("/api/radio/tune", json={"mode": "manual", "freq_mhz": 5000}).status_code == 422
    r = client.put("/api/radio/tune", json={"mode": "manual", "freq_mhz": 155.16, "modulation": "nfm", "minutes": 30})
    assert r.status_code == 200, r.text
    assert r.json()["tune"]["freq_mhz"] == 155.16 and r.json()["tune"]["until"].endswith("Z")
    conf = (_config.RADIO_DIR / "rtl_airband.conf").read_text()
    assert "freq = 155.1600" in conf and "centerfreq = 155.2600" in conf and 'filename_template = "dev1"' in conf
    assert 'mode = "scan"' not in conf
    status = client.get("/api/radio/status").json()
    assert status["tune"]["by"] == "Member" and status["live"][0]["mode"] == "manual"
    # Time's up: back to scanning on its own.
    with SessionLocal() as db:
        t = state.get(db, "radio_tune")
        state.put(db, "radio_tune", {**t, "until": "2000-01-01T00:00:00"})
    _rf._expire_tuning()
    conf = (_config.RADIO_DIR / "rtl_airband.conf").read_text()
    assert 'mode = "scan"' in conf and client.get("/api/radio/status").json()["tune"] is None
    # And by hand.
    client.put("/api/radio/tune", json={"mode": "manual", "freq_mhz": 121.5, "modulation": "am", "minutes": 0})
    assert client.get("/api/radio/status").json()["tune"]["until"] is None
    client.put("/api/radio/tune", json={"mode": "scan"})
    with SessionLocal() as db:
        assert radio_config.tune_state(db) is None
