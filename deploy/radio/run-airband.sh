#!/bin/sh
# Runs RTLSDR-Airband and restarts it whenever the app rewrites its config.
CONF=/config/rtl_airband.conf
while [ ! -s "$CONF" ]; do
  echo "Waiting for $CONF — set up the radio in the app (Settings → Radio → Apply)."
  sleep 15
done
while true; do
  stamp=$(stat -c %Y "$CONF")
  if grep -q '^devices: ($' "$CONF" && ! grep -q 'type = "rtlsdr"' "$CONF"; then
    echo "Radio has no active dongles. Waiting for changes."
    while [ "$(stat -c %Y "$CONF")" = "$stamp" ]; do sleep 5; done
    continue
  fi
  /app/rtl_airband -F -e -c "$CONF" &
  pid=$!
  while kill -0 "$pid" 2>/dev/null && [ "$(stat -c %Y "$CONF")" = "$stamp" ]; do sleep 5; done
  if kill -0 "$pid" 2>/dev/null; then
    echo "Config changed; restarting recorder."
    kill "$pid"; wait "$pid"
  else
    wait "$pid"; echo "Recorder exited ($?). Restarting in 10 s."; sleep 10
  fi
done
