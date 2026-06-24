#!/usr/bin/env bash
# Hawksroost Server — confirm RTLSDR-Airband is writing recordings (Step 1)
set -uo pipefail
DIR="${1:-./recordings}"

echo "Looking for recordings in: $DIR"
if [ ! -d "$DIR" ]; then
  echo "  (directory does not exist yet)"
  exit 1
fi

mapfile -t files < <(find "$DIR" -type f -name '*.mp3' -printf '%T@ %p\n' 2>/dev/null \
                     | sort -nr | head -10 | cut -d' ' -f2-)

if [ "${#files[@]}" -eq 0 ]; then
  echo "  No .mp3 files yet."
  echo "  - Give it ~30–60s after the container starts."
  echo "  - Watch logs:   docker compose logs -f rtlsdr-airband"
  echo "  - A crash-loop usually means the SDR is busy (stop owrx) or not found."
  exit 1
fi

echo "Most recent recordings:"
for f in "${files[@]}"; do
  printf '  %5s  %s\n' "$(du -h "$f" | cut -f1)" "$f"
done
echo
echo "A NOAA file that keeps GROWING == the chain works. Play it with:"
echo "  ffplay '${files[0]}'        # or copy it off-host into any audio player"
