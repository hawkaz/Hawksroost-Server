#!/usr/bin/env bash
# Hawksroost Server — host preflight for RTLSDR-Airband (Step 1)
# Run on the cabin host BEFORE `docker compose up`. Read-only; safe to re-run.
set -uo pipefail

RTL_USB_ID="0bda:2838"   # RTL2838 — covers RTL-SDR Blog v3/v4
fail=0
ok()   { printf '  \033[32m\xe2\x9c\x93\033[0m %s\n' "$1"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$1"; }
bad()  { printf '  \033[31m\xe2\x9c\x97\033[0m %s\n' "$1"; fail=1; }

echo "== 1. Dongle present on USB =="
if lsusb | grep -qi "$RTL_USB_ID"; then
  ok "RTL-SDR found: $(lsusb | grep -i "$RTL_USB_ID")"
else
  bad "No RTL2838 ($RTL_USB_ID) on USB. Check the dongle and cable."
fi

echo "== 2. DVB kernel driver blacklisted =="
if lsmod | grep -qE 'dvb_usb_rtl28xxu|rtl2832'; then
  bad "dvb_usb_rtl28xxu is LOADED — it will fight for the dongle."
  warn "Fix: echo 'blacklist dvb_usb_rtl28xxu' | sudo tee /etc/modprobe.d/blacklist-rtl.conf && sudo rmmod dvb_usb_rtl28xxu"
else
  ok "No DVB driver loaded."
fi
if grep -rqs 'rtl28xxu' /etc/modprobe.d/ 2>/dev/null; then
  ok "Blacklist entry present in /etc/modprobe.d."
else
  warn "No blacklist file found (module not loaded now, but add one to be safe)."
fi

echo "== 3. Nothing else is holding the dongle =="
holder=""
for c in $(docker ps --format '{{.Names}}' 2>/dev/null); do
  if docker inspect "$c" --format '{{json .HostConfig.Devices}}{{.HostConfig.Privileged}}' 2>/dev/null \
       | grep -q '/dev/bus/usb\|true'; then
    holder="$holder $c"
  fi
done
if [ -n "$holder" ]; then
  warn "Container(s) with USB access:$holder"
  warn "If one is using the SDR (e.g. owrx / OpenWebRX), STOP it first:"
  warn "    docker stop$holder"
  warn "Only ONE program can own the dongle at a time."
else
  ok "No running container is mapped to /dev/bus/usb."
fi

echo "== 4. (optional) Confirm it's a v4 with rtl_test =="
if command -v rtl_test >/dev/null 2>&1; then
  warn "Run manually, Ctrl-C after a few seconds:  rtl_test -t"
  warn "Expect a line like:  'RTL-SDR Blog V4 Detected'"
  warn "(rtl_test also holds the dongle — Ctrl-C it before 'compose up'.)"
else
  warn "rtl_test not on host (fine — it also lives in the container)."
fi

echo
if [ "$fail" -eq 0 ]; then
  printf '\033[32mPREFLIGHT OK\033[0m — start with:  docker compose up -d rtlsdr-airband\n'
else
  printf '\033[31mPREFLIGHT FAILED\033[0m — fix the \xe2\x9c\x97 items above first.\n'
fi
exit "$fail"
