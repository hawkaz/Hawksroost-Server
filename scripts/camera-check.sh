#!/usr/bin/env bash
# Read-only check of the live-video chain: camera -> go2rtc -> nginx.
# Prints OK / FAIL per step. Camera passwords are masked in everything shown.
#   bash /opt/hawksroost/scripts/camera-check.sh
set -euo pipefail
cd "$(dirname "$0")/.."

mask() { sed -E 's#(rtsps?|https?)://[^@/ ]+@#\1://***@#g'; }
port=$(grep -E '^HAWK_LAN_PORT=' .env 2>/dev/null | cut -d= -f2 || true)
port=${port:-8080}

echo "== Containers"
for svc in api go2rtc web; do
  if docker compose ps --status running --services 2>/dev/null | grep -qx "$svc"; then
    echo "OK   $svc is running"
  else
    echo "FAIL $svc is not running"
  fi
done

echo
echo "== go2rtc: streams, a test picture from each, and the video format"
docker compose exec -T api python - <<'PY' 2>&1 | mask
import re
import httpx

G = "http://go2rtc:1984"

def mask(s):
    return re.sub(r"(rtsps?|https?)://[^@/\s]+@", r"\1://***@", str(s))

try:
    streams = httpx.get(f"{G}/api/streams", timeout=10).json()
except Exception as e:
    print(f"FAIL can't reach go2rtc from the api: {e}")
    raise SystemExit
names = sorted(n for n in streams if n.startswith("cam"))
if not names:
    print("FAIL go2rtc has no camera streams. The app didn't register any.")
for name in names:
    info = streams[name] or {}
    srcs = [p.get("url") for p in (info.get("producers") or []) if p.get("url")]
    print(f"--   {name}: {mask(srcs[0]) if srcs else '(no source)'}")
    try:
        r = httpx.get(f"{G}/api/frame.jpeg", params={"src": name}, timeout=25)
        if r.status_code == 200 and r.content[:2] == b"\xff\xd8":
            print(f"OK   {name}: got a picture ({len(r.content) // 1024} KB)")
        elif r.status_code == 200:
            print(f"FAIL {name}: no picture. go2rtc couldn't get video from the camera (see its log below)")
        else:
            print(f"FAIL {name}: no picture (HTTP {r.status_code}) {mask(r.text[:200]).strip()}")
    except Exception as e:
        print(f"FAIL {name}: no picture ({e})")
    try:
        detail = httpx.get(f"{G}/api/streams", params={"src": name}, timeout=10).json()
        medias = []
        for p in detail.get("producers") or []:
            medias += [m for m in (p.get("medias") or []) if "video" in m or "audio" in m]
        print(f"--   {name} format: {'; '.join(medias) if medias else 'unknown (not connected)'}")
    except Exception as e:
        print(f"--   {name} format: unknown ({e})")
PY

echo
echo "== nginx: video player files and sign-in guard"
code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:${port}/video/video-stream.js" || true)
if [ "$code" = "200" ]; then echo "OK   player script loads (200)"; else echo "FAIL player script: HTTP $code"; fi
code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:${port}/video/api/ws?src=cam1_sub" || true)
if [ "$code" = "401" ]; then echo "OK   live video needs sign-in (401 without it)"; else echo "FAIL live video guard: HTTP $code (expected 401)"; fi

echo
echo "== Recent go2rtc log (passwords masked)"
docker compose logs --no-log-prefix --tail 25 go2rtc 2>&1 | mask

echo
echo "== Recent camera lines from the api log (passwords masked)"
docker compose logs --no-log-prefix --tail 400 api 2>&1 | grep -E "hawk\.(cameras|go2rtc)" | tail -15 | mask || echo "--   none"
