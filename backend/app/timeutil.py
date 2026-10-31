from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from . import config

LOCAL_TZ = ZoneInfo(config.TZ_NAME)


def utcnow() -> datetime:
    """Naive UTC — what we store in SQLite."""
    return datetime.now(UTC).replace(tzinfo=None)


def iso(dt: datetime | None) -> str | None:
    """Serialize a stored (naive UTC) datetime for the browser."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def local_today():
    return datetime.now(LOCAL_TZ).date()
