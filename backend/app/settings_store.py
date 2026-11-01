"""Admin-editable integration settings, stored in the `settings` table.

Each section has defaults and a list of secret fields. Secrets are write-only:
the API never sends them back to the browser, only whether they are set.
"""
from copy import deepcopy
from typing import Any

from sqlalchemy.orm import Session

from .models import Setting

SECTIONS: dict[str, dict[str, Any]] = {
    "general": {
        "site_name": "Hawksroost",
        "public_url": "",          # e.g. https://hawksroost.live — used in links, emails, OAuth
        "units": "imperial",       # imperial | metric
        "login_photo": "",         # content type of data/branding/login-photo, "" = none
        "login_photo_v": 0,        # bumps on each upload so browsers refetch
    },
    "google": {
        "enabled": False,
        "client_id": "",
        "client_secret": "",
    },
    "email": {
        "enabled": False,
        "host": "smtp-relay.brevo.com",
        "port": 587,
        "username": "",
        "password": "",
        "from_email": "",
        "from_name": "Hawksroost",
    },
    "tempest": {
        "enabled": True,
        "serial": "",              # optional: only accept this station's packets
        "api_token": "",           # optional: Tempest personal access token, for the forecast
        "station_id": "",
        "elevation_ft": 0,         # station height, to show sea-level pressure; 0 = show station pressure
    },
    "starlink": {
        "enabled": True,
        "address": "192.168.100.1:9200",
    },
    "alerts": {
        "default_cooldown_s": 300,
    },
    "radio": {
        "enabled": False,
        "max_storage_gb": 20,
        "max_age_days": 30,
        "incident_tx_count": 6,
        "incident_window_min": 10,
        "incident_cooldown_min": 15,
    },
    "backup": {
        "enabled": True,
        "keep_days": 14,
        "hour": 3,
    },
    # Generated automatically; not shown in the UI.
    "push": {
        "vapid_private_pem": "",
        "vapid_public_key": "",
        "contact": "",
    },
}

SECRETS: dict[str, set[str]] = {
    "google": {"client_secret"},
    "email": {"password"},
    "tempest": {"api_token"},
    "push": {"vapid_private_pem"},
}

HIDDEN_SECTIONS = {"push"}


def get(db: Session, section: str) -> dict[str, Any]:
    """Full settings for a section, including secrets. Server-side use only."""
    values = deepcopy(SECTIONS[section])
    row = db.get(Setting, section)
    if row and row.value:
        values.update({k: v for k, v in row.value.items() if k in values})
    return values


def public(db: Session, section: str) -> dict[str, Any]:
    """Settings safe to send to an admin's browser: secrets replaced by `<name>_set` flags."""
    values = get(db, section)
    for key in SECRETS.get(section, ()):
        values[f"{key}_set"] = bool(values.pop(key))
    return values


def update(db: Session, section: str, changes: dict[str, Any]) -> dict[str, Any]:
    """Merge changes into a section. A secret sent as None/missing is left unchanged; "" clears it."""
    defaults = SECTIONS[section]
    current = get(db, section)
    for key, value in changes.items():
        if key not in defaults:
            continue
        if key in SECRETS.get(section, ()) and value is None:
            continue
        default = defaults[key]
        if isinstance(default, bool):
            value = bool(value)
        elif isinstance(default, int) and value is not None and value != "":
            value = int(value)
        elif isinstance(default, str):
            value = "" if value is None else str(value).strip()
        current[key] = value
    row = db.get(Setting, section)
    if row is None:
        row = Setting(key=section, value=current)
        db.add(row)
    else:
        row.value = current
    db.commit()
    return current
