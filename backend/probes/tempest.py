"""Listen for Tempest UDP broadcasts for 70 seconds and print what arrives.

    docker compose stop collector
    docker compose run --rm collector python -m probes.tempest
    docker compose start collector

(The collector normally holds UDP port 50222.)
"""
import json
import socket
import time

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sock.bind(("0.0.0.0", 50222))
sock.settimeout(5)
print("Listening on UDP 50222 for 70 seconds...")
end, seen = time.time() + 70, {}
while time.time() < end:
    try:
        data, addr = sock.recvfrom(4096)
    except socket.timeout:
        continue
    msg = json.loads(data)
    kind = msg.get("type")
    seen[kind] = seen.get(kind, 0) + 1
    if kind != "rapid_wind" or seen[kind] == 1:
        print(addr[0], json.dumps(msg)[:300])
print("\nSummary:", seen or "NOTHING RECEIVED — is the hub on the same network as this laptop?")
