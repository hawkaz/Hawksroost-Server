#!/usr/bin/env bash
# Hawksroost Server — confirm RTLSDR-Airband is writing recordings (Step 1)
set -uo pipefail
DIR="${1:-./recordings}"

echo "Looking for recordings in: $DIR"
[ -d "$DIR" ] || { echo "  (directory does not exist yet)"; exit 1; }

# RTLSDR-Airband writes <name>.mp3.tmp WHILE recording, then renames it to
# <name>.mp3 once the file finalizes: hourly rotation for a continuous channel,
# squelch-close for split_on_transmission, or on shutdown. So during active
# recording you'll see a GROWING .tmp — that's success in progress, and it's
# also why rdio-scanner's dirwatch (Step 2) only ingests the final .mp3.
mapfile -t lines < <(find "$DIR" -type f \( -name '*.mp3' -o -name '*.mp3.tmp' \) \
                     -printf '%T@\t%s\t%p\n' 2>/dev/null | sort -nr | head -10)

if [ "${#lines[@]}" -eq 0 ]; then
  echo "  No recordings yet."
  echo "  - Give it ~30–60s after the container starts."
  echo "  - Watch logs:   docker compose logs -f rtlsdr-airband"
  echo "  - A crash-loop usually means the SDR is busy (stop owrx) or not found."
  exit 1
fi

echo "Recent recordings (newest first):"
newest=""
for line in "${lines[@]}"; do
  size=$(printf '%s' "$line" | cut -f2)
  path=$(printf '%s' "$line" | cut -f3)
  [ -z "$newest" ] && newest="$path"
  human=$(numfmt --to=iec --suffix=B "$size" 2>/dev/null || echo "${size}B")
  if [[ "$path" == *.tmp ]]; then
    printf '  %9s  %s   <-- recording now\n' "$human" "$path"
  else
    printf '  %9s  %s   (finalized)\n' "$human" "$path"
  fi
done

echo
echo "A growing *.mp3.tmp means the receive -> demod -> record chain works."
echo "This host has no speaker. To LISTEN, copy the file to your laptop (a partial"
echo ".tmp is a valid MP3 and plays fine). FROM YOUR LAPTOP'S terminal, run:"
echo "  scp '$USER@<host-lan-ip>:$PWD/${newest#./}' ."
