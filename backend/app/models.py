"""Database tables. Times are naive UTC; dates (bookings) are local calendar dates."""
from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base
from .timeutil import utcnow

ROLES = ("viewer", "member", "admin")
FAMILY_COLORS = ("copper", "pine", "navy", "gold", "lake", "bark", "sage", "plum")


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    google_sub: Mapped[str | None] = mapped_column(String(64), unique=True)
    role: Mapped[str] = mapped_column(String(16), default="member")
    color: Mapped[str] = mapped_column(String(16), default="copper")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    ical_token: Mapped[str] = mapped_column(String(64), unique=True)
    mute_until: Mapped[datetime | None] = mapped_column(DateTime)
    notify_bookings: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_radio: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime)


class AuthSession(Base):
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # sha256 of the cookie token
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    user_agent: Mapped[str | None] = mapped_column(String(255))
    persistent: Mapped[bool] = mapped_column(Boolean, default=True)  # "Remember me"
    user: Mapped[User] = relationship()


class AccessRequest(Base):
    """Someone asked for an account from the sign-in page."""
    __tablename__ = "access_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    email: Mapped[str] = mapped_column(String(254))
    message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    handled_at: Mapped[datetime | None] = mapped_column(DateTime)
    outcome: Mapped[str | None] = mapped_column(String(16))  # invited | dismissed


class Invite(Base):
    __tablename__ = "invites"
    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    email: Mapped[str | None] = mapped_column(String(254))
    name: Mapped[str | None] = mapped_column(String(80))
    role: Mapped[str] = mapped_column(String(16), default="member")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used_at: Mapped[datetime | None] = mapped_column(DateTime)
    used_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class PasswordReset(Base):
    __tablename__ = "password_resets"
    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used_at: Mapped[datetime | None] = mapped_column(DateTime)


class Setting(Base):
    """Admin-editable configuration, one JSON blob per section (google, email, tempest, ...)."""
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class KeyValue(Base):
    """Small live-state values written by background jobs (last Tempest packet, Starlink status...)."""
    __tablename__ = "kv_state"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    endpoint: Mapped[str] = mapped_column(Text, unique=True)
    p256dh: Mapped[str] = mapped_column(String(255))
    auth: Mapped[str] = mapped_column(String(255))
    device_label: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_ok_at: Mapped[datetime | None] = mapped_column(DateTime)
    fail_count: Mapped[int] = mapped_column(Integer, default=0)


# --- Cameras -----------------------------------------------------------------

class Camera(Base):
    __tablename__ = "cameras"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(16), default="reolink")  # reolink | onvif | stream
    host: Mapped[str] = mapped_column(String(255))
    port: Mapped[int | None] = mapped_column(Integer)
    username: Mapped[str] = mapped_column(String(80), default="")
    password: Mapped[str] = mapped_column(String(255), default="")
    options: Mapped[dict] = mapped_column(JSON, default=dict)  # per-kind extras (stream URLs, ...)
    channel: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    sort: Mapped[int] = mapped_column(Integer, default=0)
    cooldown_s: Mapped[int] = mapped_column(Integer, default=300)
    # Filled in from the camera on connect.
    model: Mapped[str | None] = mapped_column(String(80))
    firmware: Mapped[str | None] = mapped_column(String(80))
    capabilities: Mapped[dict] = mapped_column(JSON, default=dict)
    last_ok_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_error: Mapped[str | None] = mapped_column(Text)


class AlertPref(Base):
    __tablename__ = "alert_prefs"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    camera_id: Mapped[int] = mapped_column(ForeignKey("cameras.id", ondelete="CASCADE"))
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    types: Mapped[list] = mapped_column(JSON, default=lambda: ["person", "vehicle"])
    mute_until: Mapped[datetime | None] = mapped_column(DateTime)


class CameraEvent(Base):
    __tablename__ = "camera_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    camera_id: Mapped[int] = mapped_column(ForeignKey("cameras.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(32))
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    snapshot: Mapped[str | None] = mapped_column(String(255))
    notified: Mapped[int] = mapped_column(Integer, default=0)


# --- Household ---------------------------------------------------------------

class Reservation(Base):
    __tablename__ = "reservations"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16), default="stay")  # stay | logistics
    title: Mapped[str] = mapped_column(String(120))
    start_date: Mapped[date] = mapped_column(Date, index=True)
    end_date: Mapped[date] = mapped_column(Date)  # departure day for stays; same as start for logistics
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    user: Mapped[User] = relationship()


class ShoppingItem(Base):
    __tablename__ = "shopping_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    text: Mapped[str] = mapped_column(String(200))
    qty: Mapped[str | None] = mapped_column(String(40))
    store: Mapped[str | None] = mapped_column(String(60))
    added_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    added_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    acquired_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    acquired_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)


class TaskList(Base):
    __tablename__ = "task_lists"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    sort: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    list_id: Mapped[int] = mapped_column(ForeignKey("task_lists.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text)
    priority: Mapped[int] = mapped_column(Integer, default=1)  # 0 low, 1 normal, 2 high
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    due_date: Mapped[date | None] = mapped_column(Date)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    done_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    done_at: Mapped[datetime | None] = mapped_column(DateTime)


# --- Weather & Starlink --------------------------------------------------------

class WeatherObs(Base):
    """One Tempest `obs_st` report (about once a minute). Metric units as sent."""
    __tablename__ = "weather_obs"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, index=True)
    serial: Mapped[str | None] = mapped_column(String(32))
    temp_c: Mapped[float | None] = mapped_column(Float)
    humidity: Mapped[float | None] = mapped_column(Float)
    pressure_mb: Mapped[float | None] = mapped_column(Float)
    wind_lull: Mapped[float | None] = mapped_column(Float)
    wind_avg: Mapped[float | None] = mapped_column(Float)
    wind_gust: Mapped[float | None] = mapped_column(Float)
    wind_dir: Mapped[float | None] = mapped_column(Float)
    illuminance: Mapped[float | None] = mapped_column(Float)
    uv: Mapped[float | None] = mapped_column(Float)
    solar: Mapped[float | None] = mapped_column(Float)
    rain_mm: Mapped[float | None] = mapped_column(Float)
    precip_type: Mapped[int | None] = mapped_column(Integer)
    strike_count: Mapped[int | None] = mapped_column(Integer)
    strike_avg_km: Mapped[float | None] = mapped_column(Float)
    battery: Mapped[float | None] = mapped_column(Float)


class WeatherEvent(Base):
    __tablename__ = "weather_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, index=True)
    kind: Mapped[str] = mapped_column(String(16))  # strike | rain_start
    distance_km: Mapped[float | None] = mapped_column(Float)
    energy: Mapped[float | None] = mapped_column(Float)


class StarlinkSample(Base):
    """One-minute rollup of the dish's per-second history."""
    __tablename__ = "starlink_samples"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, index=True, unique=True)
    latency_ms: Mapped[float | None] = mapped_column(Float)
    drop_rate: Mapped[float | None] = mapped_column(Float)
    down_bps: Mapped[float | None] = mapped_column(Float)
    up_bps: Mapped[float | None] = mapped_column(Float)
    down_bytes: Mapped[float] = mapped_column(Float, default=0)   # unused (usage counters dropped)
    up_bytes: Mapped[float] = mapped_column(Float, default=0)     # unused
    down_peak_bps: Mapped[float | None] = mapped_column(Float)
    up_peak_bps: Mapped[float | None] = mapped_column(Float)
    power_w: Mapped[float | None] = mapped_column(Float)
    obstructed_s: Mapped[int] = mapped_column(Integer, default=0)
    outage_s: Mapped[int] = mapped_column(Integer, default=0)     # seconds with every ping dropped
    seconds: Mapped[int] = mapped_column(Integer, default=0)


# --- Radio -------------------------------------------------------------------

class RadioDevice(Base):
    __tablename__ = "radio_devices"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(60))
    serial: Mapped[str | None] = mapped_column(String(32))
    index: Mapped[int] = mapped_column(Integer, default=0)
    gain: Mapped[float] = mapped_column(Float, default=32.0)
    correction: Mapped[int] = mapped_column(Integer, default=0)
    mode: Mapped[str] = mapped_column(String(16), default="auto")  # auto | scan | multichannel
    centerfreq: Mapped[float | None] = mapped_column(Float)
    live_stream: Mapped[bool] = mapped_column(Boolean, default=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class RadioChannel(Base):
    __tablename__ = "radio_channels"
    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int | None] = mapped_column(ForeignKey("radio_devices.id", ondelete="SET NULL"))
    group: Mapped[str] = mapped_column(String(40))
    label: Mapped[str] = mapped_column(String(80))
    freq_mhz: Mapped[float] = mapped_column(Float)
    modulation: Mapped[str] = mapped_column(String(8), default="nfm")
    squelch_snr: Mapped[float | None] = mapped_column(Float)
    ctcss: Mapped[float | None] = mapped_column(Float)  # repeater tone (Hz); None = carrier squelch
    incident: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    sort: Mapped[int] = mapped_column(Integer, default=0)


class RadioIncident(Base):
    __tablename__ = "radio_incidents"
    id: Mapped[int] = mapped_column(primary_key=True)
    channel_id: Mapped[int | None] = mapped_column(ForeignKey("radio_channels.id", ondelete="SET NULL"))
    label: Mapped[str] = mapped_column(String(80))
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_activity_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime)
    tx_count: Mapped[int] = mapped_column(Integer, default=0)


class RadioRecording(Base):
    __tablename__ = "radio_recordings"
    id: Mapped[int] = mapped_column(primary_key=True)
    channel_id: Mapped[int | None] = mapped_column(ForeignKey("radio_channels.id", ondelete="SET NULL"), index=True)
    freq_mhz: Mapped[float | None] = mapped_column(Float)
    label: Mapped[str] = mapped_column(String(80))
    started_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    duration_s: Mapped[float] = mapped_column(Float, default=0)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    path: Mapped[str] = mapped_column(String(255), unique=True)
    keep: Mapped[bool] = mapped_column(Boolean, default=False)
    incident_id: Mapped[int | None] = mapped_column(ForeignKey("radio_incidents.id", ondelete="SET NULL"))
    parts: Mapped[int] = mapped_column(Integer, default=1)   # transmissions joined into this call
