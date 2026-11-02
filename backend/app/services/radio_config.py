"""Turn the radio devices and channels in the database into RTLSDR-Airband and
Icecast config files. The recorder container restarts itself when its file changes.

Mode per dongle:
- multichannel: every enabled channel fits inside the dongle's ~2 MHz window and
  is heard at the same time.
- scan: channels are spread wider; the dongle hops between them.
- manual: someone tuned the dongle to one frequency from the Radio page
  (kv_state "radio_tune"); scanning stops until it goes back to scan.
"""
from datetime import datetime
import secrets
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config, settings_store, state
from ..timeutil import utcnow
from ..models import RadioChannel, RadioDevice
from .radio_stats import STATS_NAME

MIN_MHZ, MAX_MHZ = 24.0, 1766.0   # what an RTL-SDR tunes
MANUAL_OFFSET_MHZ = 0.1           # tune just off the wanted frequency, away from the DC spike
WINDOW_MHZ = 1.6          # usable span we allow for multichannel (2.4 Msps, with margin)
DC_GUARD_MHZ = 0.03       # keep channels off the centre-frequency DC spike
DEFAULT_SQUELCH = 9.0     # dB SNR
NFM_BANDWIDTH = 12000
RECORDINGS_IN_CONTAINER = "/recordings"
# Sound, set in the recorder (applies to recordings and live listening):
# - Its MP3 encoder keeps 100–2500 Hz by default, which sounds muffled and lets the
#   sub-audible tone hum through (CTCSS tones are 67–254 Hz). Speech: 300–3400 Hz.
# - Narrowband FM comes out quiet: ±2.5 kHz deviation is about a third of full scale
#   before any boost. `ampfactor` multiplies it (clipped at full scale), FM only: AM
#   already levels itself.
VOICE_HIGHPASS_HZ = 300
VOICE_LOWPASS_HZ = 3400
DEFAULT_BOOST = 3.0


@dataclass
class DevicePlan:
    device: RadioDevice
    mode: str
    channels: list[RadioChannel]
    centerfreq: float | None = None
    errors: list[str] = field(default_factory=list)


def _q(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', "'") + '"'


def plan_device(dev: RadioDevice, channels: list[RadioChannel]) -> DevicePlan:
    chans = sorted(channels, key=lambda c: c.freq_mhz)
    if not chans:
        return DevicePlan(dev, "off", [], errors=["No channels turned on"])
    lo, hi = chans[0].freq_mhz, chans[-1].freq_mhz
    fits = (hi - lo) <= WINDOW_MHZ
    mode = dev.mode if dev.mode != "auto" else ("multichannel" if fits else "scan")
    plan = DevicePlan(dev, mode, chans)
    if mode == "multichannel":
        center = dev.centerfreq or round((lo + hi) / 2, 4)
        if any(abs(c.freq_mhz - center) < DC_GUARD_MHZ for c in chans):
            center = round(center + 2 * DC_GUARD_MHZ, 4)
        plan.centerfreq = center
        outside = [c for c in chans if abs(c.freq_mhz - center) > WINDOW_MHZ / 2]
        if outside:
            plan.errors.append(
                "These don't fit in one dongle's window around "
                f"{center:.3f} MHz: " + ", ".join(f"{c.label} ({c.freq_mhz:.4f})" for c in outside)
                + ". Use scan mode or another dongle.")
    return plan


def tune_state(db: Session) -> dict | None:
    """Current manual tuning, or None when scanning. Expired tuning counts as scanning."""
    t = state.get(db, "radio_tune")
    if not t:
        return None
    if t.get("until") and datetime.fromisoformat(t["until"]) <= utcnow():
        return None
    return t


def manual_plan(dev: RadioDevice, freq_mhz: float, modulation: str) -> DevicePlan:
    ch = RadioChannel(id=0, device_id=dev.id, group="Manual", label=f"{freq_mhz:.4f} MHz", freq_mhz=freq_mhz,
                      modulation=modulation, squelch_snr=None, ctcss=None, incident=False, enabled=True)
    return DevicePlan(dev, "manual", [ch], centerfreq=round(freq_mhz + MANUAL_OFFSET_MHZ, 4))


def build_plans(db: Session) -> list[DevicePlan]:
    plans = []
    tune = tune_state(db)
    for dev in db.scalars(select(RadioDevice).where(RadioDevice.enabled).order_by(RadioDevice.id)):
        if tune and tune.get("device_id") == dev.id:
            plans.append(manual_plan(dev, float(tune["freq_mhz"]), tune.get("modulation", "nfm")))
            continue
        chans = list(db.scalars(select(RadioChannel).where(
            RadioChannel.device_id == dev.id, RadioChannel.enabled)))
        plans.append(plan_device(dev, chans))
    return plans


def icecast_password(db: Session) -> str:
    """Source password shared by the recorder and Icecast. Generated once, kept in kv_state."""
    s = state.get(db, "radio_secrets") or {}
    if not s.get("source"):
        s = {"source": secrets.token_urlsafe(18), "admin": secrets.token_urlsafe(18)}
        state.put(db, "radio_secrets", s)
    return s["source"]


def _file_output(template: str) -> str:
    return ("{ type = \"file\"; directory = \"%s\"; filename_template = %s; "
            "split_on_transmission = true; include_freq = true; }" % (RECORDINGS_IN_CONTAINER, _q(template)))


def _icecast_output(mount: str, name: str, password: str, scan: bool) -> str:
    extra = " send_scan_freq_tags = true;" if scan else ""
    return ("{ type = \"icecast\"; server = \"icecast\"; port = 8000; mountpoint = %s; "
            "username = \"source\"; password = %s; name = %s;%s }" % (_q(mount), _q(password), _q(name), extra))


def _amp(modulation: str, boost: float) -> float:
    return boost if modulation == "nfm" else 1.0


def _snr(c: RadioChannel) -> float:
    return c.squelch_snr if c.squelch_snr is not None else DEFAULT_SQUELCH


VOICE = f"highpass = {VOICE_HIGHPASS_HZ}; lowpass = {VOICE_LOWPASS_HZ}; "


def mount_name(dev: RadioDevice) -> str:
    return f"dev{dev.id}"


def render_airband(plans: list[DevicePlan], password: str, boost: float = DEFAULT_BOOST) -> str:
    lines = [
        "# Generated by the Hawksroost app (Settings → Radio). Don't edit by hand.",
        "fft_size = 1024;",
        "localtime = false;  # filenames in UTC; the app converts",
        "multiple_demod_threads = true;",
        "multiple_output_threads = true;",
        # What it hears on each frequency, every 15 s; the app shows it in Admin → Radio.
        f"stats_filepath = {_q(RECORDINGS_IN_CONTAINER + '/' + STATS_NAME)};",
    ]
    mixers = []
    devices = []
    for p in plans:
        if p.mode == "off" or p.errors:
            continue
        d = p.device
        head = ['type = "rtlsdr";', f'serial = {_q(d.serial)};' if d.serial else f"index = {d.index};",
                f"gain = {d.gain:.1f};", f"correction = {d.correction};"]
        if p.mode == "manual":
            # Files named like scan mode (dev<id>…_<freq>.mp3), so a frequency that's also a saved
            # channel is labelled with that channel's name.
            c = p.channels[0]
            outputs = [_file_output(f"dev{d.id}")]
            if d.live_stream:
                outputs.append(_icecast_output(mount_name(d), d.name, password, scan=False))
            chan = ("{ freq = %.4f; label = %s; modulation = %s; bandwidth = %d; squelch_snr_threshold = %.1f; "
                    "ampfactor = %.1f; %soutputs: ( %s ); }" % (
                        c.freq_mhz, _q(c.label), _q(c.modulation), NFM_BANDWIDTH, DEFAULT_SQUELCH,
                        _amp(c.modulation, boost), VOICE, ", ".join(outputs)))
            devices.append("  {\n    " + "\n    ".join(head) + f"\n    centerfreq = {p.centerfreq:.4f};\n"
                           "    channels: (\n      " + chan + "\n    );\n  }")
            continue
        if p.mode == "scan":
            freqs = ", ".join(f"{c.freq_mhz:.4f}" for c in p.channels)
            labels = ", ".join(_q(c.label) for c in p.channels)
            mods = {c.modulation for c in p.channels}
            # Each frequency keeps its own squelch and volume (lists, one value per frequency).
            squelch = ", ".join(f"{_snr(c):.1f}" for c in p.channels)
            amps = ", ".join(f"{_amp(c.modulation, boost):.1f}" for c in p.channels)
            # One tone per frequency; 0 = no tone (RTLSDR-Airband treats 0 as "off" in a list).
            ctcss = ("ctcss = (" + ", ".join(f"{c.ctcss or 0:.1f}" for c in p.channels) + "); "
                     if any(c.ctcss for c in p.channels) else "")
            outputs = [_file_output(f"dev{d.id}")]
            if d.live_stream:
                outputs.append(_icecast_output(mount_name(d), d.name, password, scan=True))
            mod_line = (f"modulation = {_q(mods.pop())};" if len(mods) == 1 else
                        "modulations = (" + ", ".join(_q(c.modulation) for c in p.channels) + ");")
            chan = ("{ freqs = (%s); labels = (%s); %s bandwidth = %d; squelch_snr_threshold = (%s); %s"
                    "ampfactor = (%s); %soutputs: ( %s ); }" % (freqs, labels, mod_line, NFM_BANDWIDTH, squelch, ctcss,
                                                               amps, VOICE, ", ".join(outputs)))
            devices.append("  {\n    " + "\n    ".join(head) + '\n    mode = "scan";\n    channels: (\n      '
                           + chan + "\n    );\n  }")
        else:
            chans = []
            mixer = f"mix{d.id}"
            for c in p.channels:
                outputs = [_file_output(f"ch{c.id}")]
                if d.live_stream:
                    outputs.append('{ type = "mixer"; name = %s; }' % _q(mixer))
                tone = f"ctcss = {c.ctcss:.1f}; " if c.ctcss else ""
                chans.append(
                    "{ freq = %.4f; label = %s; modulation = %s; bandwidth = %d; squelch_snr_threshold = %.1f; %s"
                    "ampfactor = %.1f; %soutputs: ( %s ); }" % (c.freq_mhz, _q(c.label), _q(c.modulation), NFM_BANDWIDTH,
                                                               _snr(c), tone, _amp(c.modulation, boost), VOICE,
                                                               ", ".join(outputs)))
            if d.live_stream:
                mixers.append("  %s: { outputs: ( %s ); };" % (
                    mixer, _icecast_output(mount_name(d), d.name, password, scan=False)))
            devices.append("  {\n    " + "\n    ".join(head) + f"\n    centerfreq = {p.centerfreq:.4f};\n"
                           "    channels: (\n      " + ",\n      ".join(chans) + "\n    );\n  }")
    if mixers:
        lines.append("mixers: {\n" + "\n".join(mixers) + "\n};")
    lines.append("devices: (\n" + ",\n".join(devices) + "\n);")
    return "\n".join(lines) + "\n"


def render_icecast(db: Session) -> str:
    s = state.get(db, "radio_secrets") or {}
    return f"""<icecast>
  <location>Cabin</location>
  <admin>admin@localhost</admin>
  <!-- No burst of older audio for a new listener: the app sends each listener a few
       seconds of silence first so players start at once (services/radio_live.py), and
       a burst would only add delay (8 KB of quiet-channel audio is ~17 s). -->
  <limits><clients>20</clients><sources>8</sources><burst-on-connect>0</burst-on-connect></limits>
  <authentication>
    <source-password>{s.get("source", "")}</source-password>
    <admin-user>admin</admin-user>
    <admin-password>{s.get("admin", "")}</admin-password>
  </authentication>
  <hostname>icecast</hostname>
  <listen-socket><port>8000</port></listen-socket>
  <fileserve>1</fileserve>
  <paths>
    <basedir>/usr/share/icecast</basedir>
    <logdir>/tmp</logdir>
    <webroot>/usr/share/icecast/web</webroot>
    <adminroot>/usr/share/icecast/admin</adminroot>
  </paths>
  <logging><accesslog>-</accesslog><errorlog>-</errorlog><loglevel>2</loglevel></logging>
  <security><chroot>0</chroot></security>
</icecast>
"""


def _write(path, text: str) -> bool:
    """Write only when changed, atomically. Returns True if the file changed."""
    if path.exists() and path.read_text() == text:
        return False
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    tmp.replace(path)
    return True


def apply(db: Session) -> dict:
    """Validate and write config files. Returns a summary for the admin page."""
    config.RADIO_DIR.mkdir(parents=True, exist_ok=True)
    password = icecast_password(db)
    plans = build_plans(db)
    errors = [f"{p.device.name}: {e}" for p in plans for e in p.errors if p.mode != "off"]
    radio = settings_store.get(db, "radio")
    enabled = radio["enabled"]
    text = render_airband(plans if enabled else [], password, boost=float(radio["volume_boost"]))
    changed = _write(config.RADIO_DIR / "rtl_airband.conf", text)
    _write(config.RADIO_DIR / "icecast.xml", render_icecast(db))
    summary = {
        "changed": changed, "errors": errors,
        "devices": [{"id": p.device.id, "name": p.device.name, "mode": p.mode, "centerfreq": p.centerfreq,
                     "channels": len(p.channels), "mount": mount_name(p.device) if p.device.live_stream else None}
                    for p in plans],
    }
    state.put(db, "radio_plan", summary)
    return summary
