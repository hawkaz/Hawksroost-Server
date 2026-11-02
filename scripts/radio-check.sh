#!/usr/bin/env bash
# Read-only check of the radio: recorder, live listening, what the recorder hears.
# Changes nothing. No sudo. Send Claude the output if something says FAIL.
#   bash /opt/hawksroost/scripts/radio-check.sh
set -uo pipefail
cd "$(dirname "$0")/.."
ok()   { echo "OK   $1"; }
fail() { echo "FAIL $1"; }

running=$(docker compose ps --status running --services 2>/dev/null)
for svc in api web airband icecast; do
  if echo "$running" | grep -qx "$svc"; then ok "$svc is running"; else fail "$svc is not running"; fi
done

# Which live streams Icecast has, asked from the app's container (same Docker network).
mounts=$(docker compose exec -T api python -c "
from app.services import radio_live
m = radio_live.mounts()
print('no-answer' if m is None else (','.join(sorted(m)) or 'none'))" 2>/dev/null | tail -1)
case "$mounts" in
  no-answer|"") fail "Icecast (live listening) isn't answering" ;;
  none)         fail "Icecast is running, but the recorder isn't sending to it" ;;
  *)            ok "live streams: $mounts" ;;
esac

stats=data/radio/recordings/.recorder-stats.txt
if [ -s "$stats" ]; then
  age=$(( $(date +%s) - $(stat -c %Y "$stats") ))
  if [ "$age" -lt 120 ]; then ok "recorder is reporting what it hears (${age} s ago)"; else fail "recorder's report is ${age} s old (it writes every 15 s)"; fi
else
  fail "no report from the recorder yet (it starts once the recorder runs the new settings)"
fi

echo "--   recorder and Icecast (last lines about the live stream):"
docker compose logs --no-log-prefix --tail=300 airband 2>/dev/null | grep -E "Connected to|Could not connect|Lost connection|reconnect" | tail -4
docker compose logs --no-log-prefix --tail=300 icecast 2>/dev/null | grep -viE '"GET /(dev[0-9]+|status-json)' | tail -4
