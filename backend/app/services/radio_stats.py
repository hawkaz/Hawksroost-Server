"""What the recorder hears on each frequency, from its stats file.

RTLSDR-Airband (checked in the v5.2.0 source) writes `stats_filepath` every 15 seconds
in Prometheus text format, one line per metric and frequency, e.g.

    channel_squelch_counter{freq="155.618",label="Mormon Lake FD dispatch"}	12

Its counters start from zero each time the recorder restarts (a retune, Apply), so the
app adds up the increases into running totals, kept until an admin starts counting again.
Levels (noise, signal) are snapshots: the noise floor is the latest; the signal is the
strongest seen.
"""
import math
import re

from sqlalchemy.orm import Session

from .. import config, state
from ..timeutil import iso, utcnow

STATS_NAME = ".recorder-stats.txt"   # in the recordings folder; not a recording (no .mp3)
LOOPS_PER_S = 8                      # the activity counter ticks once per 1/8 s of audio with signal

COUNTERS = {
    "channel_activity_counter": "active",    # loops with signal (÷ 8 = seconds on the air)
    "channel_squelch_counter": "opens",      # times the squelch opened
    "channel_flappy_counter": "flappy",      # opened and closed again quickly: a weak signal
    "channel_ctcss_counter": "tone",         # 0.4 s windows with the channel's tone
    "channel_no_ctcss_counter": "no_tone",   # 0.4 s windows with a signal but not the tone
}
LEVELS = {"channel_dbfs_noise_level": "noise_dbfs", "channel_dbfs_signal_level": "signal_dbfs"}
LINE = re.compile(r'^(?P<name>\w+)\{freq="(?P<freq>[\d.]+)"(?:,label="[^"]*")?\}\s+(?P<value>\S+)$')


def parse(text: str) -> dict[str, dict[str, float]]:
    """Stats file → {"155.618": {"opens": 12, "noise_dbfs": -38.2, ...}}."""
    out: dict[str, dict[str, float]] = {}
    for line in text.splitlines():
        m = LINE.match(line.strip())
        if not m:
            continue
        key = COUNTERS.get(m["name"]) or LEVELS.get(m["name"])
        if not key:
            continue
        try:
            value = float(m["value"])
        except ValueError:
            continue
        if math.isfinite(value):
            out.setdefault(m["freq"], {})[key] = value
    return out


def _path():
    return config.RECORDINGS_DIR / STATS_NAME


_seen_mtime: float | None = None


def update(db: Session) -> bool:
    """Fold a new stats file into the running totals. Cheap when nothing changed."""
    global _seen_mtime
    path = _path()
    try:
        mtime = path.stat().st_mtime
    except FileNotFoundError:
        return False
    if mtime == _seen_mtime:
        return False
    _seen_mtime = mtime
    now_raw = parse(path.read_text(errors="replace"))
    s = state.get(db, "radio_stats") or {}
    totals: dict = s.get("totals", {})
    last_raw: dict = s.get("raw", {})
    levels: dict = s.get("levels", {})
    # Any counter going down means the recorder restarted: everything counts from zero again.
    restarted = any(v < last_raw.get(f, {}).get(k, 0.0)
                    for f, vals in now_raw.items() for k, v in vals.items() if k in COUNTERS.values())
    for freq, vals in now_raw.items():
        t = totals.setdefault(freq, {})
        before = last_raw.get(freq, {})
        for key in COUNTERS.values():
            if key in vals:
                t[key] = t.get(key, 0.0) + (vals[key] if restarted else max(0.0, vals[key] - before.get(key, 0.0)))
        lv = levels.setdefault(freq, {})
        if "noise_dbfs" in vals:
            lv["noise_dbfs"] = vals["noise_dbfs"]
        if "signal_dbfs" in vals and vals.get("opens", 0) > 0:
            lv["peak_dbfs"] = max(lv.get("peak_dbfs", -200.0), vals["signal_dbfs"])
    state.put(db, "radio_stats", {
        "since": s.get("since") or iso(utcnow()), "updated_at": iso(utcnow()),
        "totals": totals, "raw": now_raw, "levels": levels,
    })
    return True


def reset(db: Session) -> None:
    """Start counting again from now (the recorder's own counters carry on)."""
    s = state.get(db, "radio_stats") or {}
    state.put(db, "radio_stats", {"since": iso(utcnow()), "updated_at": s.get("updated_at"),
                                  "totals": {}, "raw": s.get("raw", {}), "levels": {}})


def for_channel(stats: dict, freq_mhz: float) -> dict | None:
    """Totals and levels for the frequency nearest freq_mhz (the file rounds to kHz)."""
    best = None
    for key in set(stats.get("totals", {})) | set(stats.get("levels", {})):
        try:
            d = abs(float(key) - freq_mhz)
        except ValueError:
            continue
        if d < 0.0011 and (best is None or d < best[0]):
            best = (d, key)
    if best is None:
        return None
    t = stats.get("totals", {}).get(best[1], {})
    lv = stats.get("levels", {}).get(best[1], {})
    return {
        "opens": int(t.get("opens", 0)), "on_air_s": round(t.get("active", 0) / LOOPS_PER_S),
        "flappy": int(t.get("flappy", 0)), "tone": int(t.get("tone", 0)), "no_tone": int(t.get("no_tone", 0)),
        "noise_dbfs": lv.get("noise_dbfs"), "peak_dbfs": lv.get("peak_dbfs"),
    }


def heard(db: Session, channels) -> dict:
    """For Admin → Radio: what each channel has had since counting started."""
    s = state.get(db, "radio_stats") or {}
    return {"since": s.get("since"), "updated_at": s.get("updated_at"),
            "channels": {c.id: for_channel(s, c.freq_mhz) for c in channels}}
