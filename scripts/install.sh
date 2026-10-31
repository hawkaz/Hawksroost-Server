#!/usr/bin/env bash
# First-time setup (safe to re-run). Run from the repo folder:
#   cd /opt/hawksroost && bash scripts/install.sh
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== Checking Docker"
docker compose version >/dev/null || { echo "FAIL: docker compose not available"; exit 1; }
docker ps >/dev/null || { echo "FAIL: this user can't run docker. Run: sudo usermod -aG docker \$USER  then log out and back in."; exit 1; }
echo "OK"

if [ ! -f .env ]; then
  cp .env.example .env
  chmod 600 .env
  echo "== Created .env"
fi

if ! grep -q '^CLOUDFLARE_TUNNEL_TOKEN=.\+' .env; then
  echo
  echo "Paste the Cloudflare tunnel token, then press Enter (it won't show on screen):"
  read -rs token
  [ -n "$token" ] || { echo "FAIL: no token entered"; exit 1; }
  sed -i "s|^CLOUDFLARE_TUNNEL_TOKEN=.*|CLOUDFLARE_TUNNEL_TOKEN=$token|" .env
  echo "OK: token saved to .env"
fi

mkdir -p data/go2rtc data/radio/recordings data/backups data/rclone

echo "== Building and starting (first time takes a few minutes)"
docker compose up -d --build

echo "== Waiting for the app"
for _ in $(seq 1 60); do
  if docker compose exec -T api python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/ping')" >/dev/null 2>&1; then
    echo "OK: app is up"
    docker compose ps --format '  {{.Service}}: {{.Status}}'
    exit 0
  fi
  sleep 3
done
echo "FAIL: app didn't start. Show logs with: docker compose logs --tail=50 api"
exit 1
