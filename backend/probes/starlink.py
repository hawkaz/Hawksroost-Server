"""Ask the Starlink dish for its status, using the address in Settings → Starlink.

    docker compose exec collector python -m probes.starlink
"""
import json

import starlink_grpc

from app import settings_store
from app.db import SessionLocal

with SessionLocal() as db:
    address = settings_store.get(db, "starlink")["address"]
print(f"Dish address: {address}")
ctx = starlink_grpc.ChannelContext(target=address)
try:
    status, obstruction, alerts = starlink_grpc.status_data(context=ctx)
    print(json.dumps({"status": status, "alerts": {k: v for k, v in alerts.items() if v}}, indent=2, default=str))
    general, bulk = starlink_grpc.history_bulk_data(60, context=ctx)
    print("History samples available:", general)
except Exception as e:
    print("FAILED:", e)
    print("Check the laptop can reach the dish: ping 192.168.100.1")
