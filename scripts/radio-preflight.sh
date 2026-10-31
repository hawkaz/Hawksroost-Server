#!/usr/bin/env bash
# Checks before turning on the radio recorder. Read-only.
#   bash /opt/hawksroost/scripts/radio-preflight.sh
set -uo pipefail
fail=0
ok()  { echo "  OK    $1"; }
bad() { echo "  FIX   $1"; fail=1; }

if lsusb | grep -qi 0bda:2838; then ok "RTL-SDR found: $(lsusb | grep -i 0bda:2838)"; else bad "No RTL-SDR on USB. Check the dongle and cable."; fi

if lsmod | grep -qE 'dvb_usb_rtl28xxu|rtl2832'; then
  bad "The TV-tuner driver has the dongle. Run:  echo 'blacklist dvb_usb_rtl28xxu' | sudo tee /etc/modprobe.d/blacklist-rtl.conf && sudo modprobe -r dvb_usb_rtl28xxu"
else
  ok "TV-tuner driver not loaded"
fi

holders=$(docker ps --format '{{.Names}}' | grep -v -E '^hawksroost|-airband-' | while read -r c; do
  docker inspect "$c" --format '{{.Name}} {{range .Mounts}}{{.Source}} {{end}}{{.HostConfig.Privileged}}' | grep -q -E '/dev/bus/usb| true$' && echo "$c"
done)
if [ -n "$holders" ]; then
  bad "These containers can use USB and may hold the dongle: $holders  — stop them (e.g. OpenWebRX) before starting the radio."
else
  ok "No other container is using USB"
fi

[ "$fail" -eq 0 ] && echo "PREFLIGHT OK" || echo "PREFLIGHT: fix the items above first"
exit "$fail"
