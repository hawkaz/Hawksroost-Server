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

if ! grep -q '^CLOUDFLARE_API_TOKEN=.\+' .env; then
  echo
  echo "Paste the Cloudflare API token (Edit zone DNS), then press Enter (it won't show on screen):"
  read -rs token
  [ -n "$token" ] || { echo "FAIL: no token entered"; exit 1; }
  sed -i "s|^CLOUDFLARE_API_TOKEN=.*|CLOUDFLARE_API_TOKEN=$token|" .env
  echo "OK: token saved to .env"
fi

echo "== Firewall: allow HTTPS from the internet (needs your sudo password)"
sudo ufw allow 80/tcp comment 'Caddy (Let'"'"'s Encrypt + redirect)' >/dev/null
sudo ufw allow 443/tcp comment 'Caddy HTTPS' >/dev/null
echo "OK: ports 80 and 443 open on the laptop"

for p in 80 443; do
  if ss -tlnH "sport = :$p" | grep -q . && ! docker ps --format '{{.Names}}' | grep -q -- '-caddy-'; then
    echo "FAIL: something else is already using port $p:"; ss -tlnpH "sport = :$p"; exit 1
  fi
done

mkdir -p data/go2rtc data/radio/recordings data/backups data/branding data/caddy/data data/caddy/config

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
