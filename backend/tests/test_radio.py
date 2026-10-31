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
