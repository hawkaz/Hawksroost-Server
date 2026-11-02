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


# --- Sound and diagnostics ---------------------------------------------------------------

def test_recorder_config_has_voice_filter_boost_and_stats():
    dev = RadioDevice(id=1, name="D", mode="auto", gain=30, correction=0, index=0, live_stream=False)
    scan = chans(155.6175, 172.3, 121.5)
    scan[1].squelch_snr = 6.0
    scan[2].modulation = "am"
    text = render_airband([plan_device(dev, scan)], "pw", boost=4.0)
    assert 'stats_filepath = "/recordings/.recorder-stats.txt";' in text
    assert "highpass = 300; lowpass = 3400;" in text
    # One value per frequency, in frequency order (121.5 AM, 155.6175, 172.3): AM isn't boosted.
    assert "ampfactor = (1.0, 4.0, 4.0);" in text
    assert "squelch_snr_threshold = (9.0, 9.0, 6.0);" in text
    multi = render_airband([plan_device(dev, chans(155.0175, 155.835))], "pw", boost=2.0)
    assert multi.count("ampfactor = 2.0;") == 2


STATS = """# HELP channel_activity_counter Loops of output_thread with frequency active.
# TYPE channel_activity_counter counter
channel_activity_counter{freq="155.618",label="Mormon Lake FD dispatch"}\t80
channel_activity_counter{freq="155.017",label="CCSO 2C"}\t4000

channel_squelch_counter{freq="155.618",label="Mormon Lake FD dispatch"}\t3
channel_squelch_counter{freq="155.017",label="CCSO 2C"}\t150
channel_no_ctcss_counter{freq="155.618",label="Mormon Lake FD dispatch"}\t40
channel_ctcss_counter{freq="155.618",label="Mormon Lake FD dispatch"}\t2
channel_dbfs_noise_level{freq="155.618",label="Mormon Lake FD dispatch"}\t-41.250
channel_dbfs_signal_level{freq="155.618",label="Mormon Lake FD dispatch"}\t-30.500
buffer_overflow_count{device="0"}\t0
"""


def test_heard_counts_survive_recorder_restarts(client, recdir):
    import os
    from app.db import SessionLocal
    from app.models import RadioChannel
    from app.services import radio_stats
    from .conftest import login
    radio_stats._seen_mtime = None
    login(client, "admin")
    with SessionLocal() as db:
        fd = RadioChannel(device_id=None, group="Fire/EMS", label="Mormon Lake FD dispatch", freq_mhz=155.6175,
                          modulation="nfm", ctcss=162.2, incident=True, enabled=True)
        so = RadioChannel(device_id=None, group="Sheriff", label="CCSO 2C", freq_mhz=155.0175,
                          modulation="nfm", ctcss=114.8, incident=False, enabled=True)
        db.add_all([fd, so])
        db.commit()
        fd_id, so_id = fd.id, so.id
    stats = recdir / radio_stats.STATS_NAME
    stats.write_text(STATS)
    with SessionLocal() as db:
        assert radio_stats.update(db) and not radio_stats.update(db)   # unchanged file: nothing to do
    # The recorder restarts (a retune): its counters start again from zero.
    stats.write_text(STATS.replace("\t80\n", "\t16\n").replace("\t3\n", "\t1\n").replace("\t40\n", "\t4\n"))
    os.utime(stats, (1, 2_000_000_000))
    with SessionLocal() as db:
        radio_stats.update(db)
    heard = client.get("/api/admin/radio").json()["heard"]
    fd_h = heard["channels"][str(fd_id)]
    assert fd_h["opens"] == 4 and fd_h["on_air_s"] == 12 and fd_h["no_tone"] == 44 and fd_h["tone"] == 4
    assert fd_h["noise_dbfs"] == -41.25 and fd_h["peak_dbfs"] == -30.5
    assert heard["channels"][str(so_id)]["on_air_s"] == 1000 and heard["since"]
    assert recdir.joinpath(radio_stats.STATS_NAME).exists() and _rf.parse_name(radio_stats.STATS_NAME) is None
    after = client.post("/api/admin/radio/heard/reset").json()["heard"]
    assert after["channels"][str(fd_id)] is None
    client.post("/api/auth/logout")
    login(client, "member")
    assert client.post("/api/admin/radio/heard/reset").status_code == 403


def _mean_db(path) -> float:
    out = _sp.run(["ffmpeg", "-hide_banner", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
                  capture_output=True, text=True).stderr
    return float(out.split("mean_volume:")[1].split("dB")[0])


@needs_ffmpeg
def test_calls_are_levelled_when_saved(recdir):
    from app.db import SessionLocal
    _settings(min_s=0, gap_s=10)
    t0 = _dt(2026, 7, 4, 18, 0, 0)
    quiet = recdir / f"ch1_{t0:%Y%m%d_%H%M%S}_154445000.mp3"
    _sp.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
             "sine=frequency=800:duration=4,volume=0.03", "-ac", "1", "-ar", "8000", "-b:a", "16k", "-f", "mp3",
             str(quiet)], check=True)
    before = _mean_db(quiet)
    with SessionLocal() as db:
        (row,) = _rf.process_files(db, now=t0 + _td(minutes=1))
        out = recdir / row.path
        assert _mean_db(out) > before + 15           # much louder
        assert 3.5 < row.duration_s < 4.6 and row.size_bytes == out.stat().st_size


@needs_ffmpeg
def test_older_calls_get_levelled_once(recdir):
    from app import state
    from app.db import SessionLocal
    from app.models import RadioRecording
    calls = recdir / _rf.CALLS
    calls.mkdir()
    old = calls / "ch1_20260704_180000_154445000.mp3"
    _sp.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
             "sine=frequency=600:duration=3,volume=0.03", "-ac", "1", "-ar", "8000", "-b:a", "16k", "-f", "mp3",
             str(old)], check=True)
    before = _mean_db(old)
    with SessionLocal() as db:
        db.add(RadioRecording(channel_id=None, label="Old", started_at=_dt(2026, 7, 4, 18), duration_s=3,
                              size_bytes=old.stat().st_size, path=f"{_rf.CALLS}/{old.name}"))
        db.commit()
        assert _rf.level_older_calls(db) == 1
        louder = _mean_db(old)
        assert louder > before + 15
        assert _rf.level_older_calls(db) == 0 and abs(_mean_db(old) - louder) < 0.5   # only once
        assert state.get(db, "radio_levelling")["done_id"] == state.get(db, "radio_levelling")["until_id"]


def test_live_listening_says_when_the_stream_is_up(client, monkeypatch):
    import httpx
    from app import settings_store
    from app.db import SessionLocal
    from app.services import radio_live
    from .conftest import login
    login(client, "admin")
    client.post("/api/admin/radio/seed")
    with SessionLocal() as db:
        settings_store.update(db, "radio", {"enabled": True})
    client.post("/api/admin/radio/apply")
    radio_live.forget()
    # Icecast down (tests point it at a closed port): unknown, and System says so.
    assert client.get("/api/radio/status").json()["live"][0]["up"] is None
    health = {i["name"]: i for i in client.get("/api/admin/health").json()["items"]}
    assert health["Live listening"]["ok"] is False and "isn't answering" in health["Live listening"]["detail"]
    # Icecast up, but the recorder isn't sending: not up.
    answers = {"icestats": {"host": "icecast"}}
    monkeypatch.setattr(radio_live.httpx, "get", lambda url, timeout: httpx.Response(200, json=answers, request=httpx.Request("GET", url)))
    radio_live.forget()
    assert client.get("/api/radio/status").json()["live"][0]["up"] is False
    # One source comes back as an object, several as a list.
    answers = {"icestats": {"source": {"listenurl": "http://icecast:8000/dev1", "listeners": 0}}}
    radio_live.forget()
    assert client.get("/api/radio/status").json()["live"][0]["up"] is True
    health = {i["name"]: i for i in client.get("/api/admin/health").json()["items"]}
    assert health["Live listening"]["ok"] is True
    answers = {"icestats": {"source": [{"listenurl": "http://icecast:8000/dev2"}, {"listenurl": "http://icecast:8000/dev1"}]}}
    radio_live.forget()
    assert client.get("/api/radio/status").json()["live"][0]["up"] is True


@needs_ffmpeg
def test_live_listening_starts_with_silence_then_the_stream(client):
    import httpx
    from app.services import radio_live
    from .conftest import login
    lead_in = radio_live.preroll()
    # Enough for a browser to start at once (Chromium waits for about 32 KB), with no tag or
    # length header that would make a player stop after it.
    assert len(lead_in) > 32_000 and lead_in[0] == 0xFF and lead_in[1] & 0xE0 == 0xE0   # starts on an MP3 frame
    assert b"ID3" not in lead_in[:10] and b"Xing" not in lead_in and b"Info" not in lead_in[:200]
    assert client.get("/api/radio/live/dev1").status_code == 401
    login(client, "viewer")
    assert client.get("/api/radio/live/..%2Fadmin").status_code == 404
    assert client.get("/api/radio/live/stats").status_code == 404
    # Icecast down (tests point it at a closed port): a plain 503.
    r = client.get("/api/radio/live/dev1")
    assert r.status_code == 503 and "isn't running" in r.json()["detail"]
    live_bytes = b"\xff\xe3" + b"\x00" * 500

    def icecast(request: httpx.Request):
        if request.url.path == "/dev1":
            return httpx.Response(200, headers={"content-type": "audio/mpeg"}, stream=httpx.ByteStream(live_bytes))
        return httpx.Response(404)

    radio_live.TRANSPORT = httpx.MockTransport(icecast)
    try:
        r = client.get("/api/radio/live/dev1")
        assert r.status_code == 200 and r.headers["content-type"] == "audio/mpeg"
        assert r.content == lead_in + live_bytes and r.headers["cache-control"] == "no-store"
        assert client.get("/api/radio/live/dev2").status_code == 503   # no such stream on Icecast
    finally:
        radio_live.TRANSPORT = None
