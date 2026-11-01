#!/bin/sh
# Runs Icecast and restarts it whenever the app rewrites its config
# (Admin → Radio → Apply), the same way the recorder wrapper works.
CONF=/config/icecast.xml
until [ -s "$CONF" ]; do
  echo "Waiting for $CONF — set up the radio in the app (Admin → Radio → Apply)."
  sleep 15
done
while true; do
  stamp=$(stat -c %Y "$CONF")
  icecast -c "$CONF" &
  pid=$!
  while kill -0 "$pid" 2>/dev/null && [ "$(stat -c %Y "$CONF")" = "$stamp" ]; do sleep 5; done
  if kill -0 "$pid" 2>/dev/null; then
    echo "Config changed; restarting Icecast."
    kill "$pid"; wait "$pid"
  else
    wait "$pid"; echo "Icecast exited ($?). Restarting in 10 s."; sleep 10
  fi
done
