#!/usr/bin/env bash
# Turn on the radio recorder containers (after Settings → Radio is set up in the app).
#   cd /opt/hawksroost && bash scripts/radio-on.sh
set -euo pipefail
cd "$(dirname "$0")/.."
bash scripts/radio-preflight.sh || { echo "Fix the preflight items first."; exit 1; }
if ! grep -q '^COMPOSE_PROFILES=.*radio' .env; then
  sed -i 's/^COMPOSE_PROFILES=\(.*\)$/COMPOSE_PROFILES=\1,radio/; s/^COMPOSE_PROFILES=,/COMPOSE_PROFILES=/' .env
  echo "Turned on radio in .env"
fi
docker compose up -d --build
sleep 10
docker compose logs --tail=15 airband
