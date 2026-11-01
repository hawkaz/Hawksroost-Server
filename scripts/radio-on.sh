#!/usr/bin/env bash
# Turn on the radio recorder, after Admin → Radio is set up and applied in the app.
# Safe to run again. No sudo.
#   bash /opt/hawksroost/scripts/radio-on.sh
set -euo pipefail
cd "$(dirname "$0")/.."

bash scripts/radio-preflight.sh || { echo "FAIL fix the items above first, then run this again"; exit 1; }

if [ -s data/radio/rtl_airband.conf ]; then
  echo "OK   radio settings found (from Admin → Radio → Apply)"
else
  echo "FAIL no radio settings yet. In the app: Admin → Radio → turn the scanner on, load the channels, press Apply."
  exit 1
fi

# The recorder and live-listening server only run when "radio" is in COMPOSE_PROFILES.
if grep -qE '^COMPOSE_PROFILES=.*\bradio\b' .env; then
  echo "OK   radio already on in .env"
elif grep -q '^COMPOSE_PROFILES=' .env; then
  sed -i 's/^COMPOSE_PROFILES=\(.*\)$/COMPOSE_PROFILES=\1,radio/; s/^COMPOSE_PROFILES=,/COMPOSE_PROFILES=/' .env
  echo "OK   turned radio on in .env"
else
  echo 'COMPOSE_PROFILES=radio' >> .env
  echo "OK   turned radio on in .env"
fi

docker compose up -d --build --remove-orphans
echo "--   waiting 15 seconds for the recorder to start"
sleep 15
running=$(docker compose ps --status running --services)
for svc in airband icecast; do
  if echo "$running" | grep -qx "$svc"; then echo "OK   $svc is running"; else echo "FAIL $svc is not running"; fi
done
echo "--   recorder log:"
docker compose logs --no-log-prefix --tail=20 airband
