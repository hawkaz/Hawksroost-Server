# Host preflight — RTL-SDR v4 on Linux

Your host (`HAWKSROOST`, Debian 13) is already in good shape from the info you
gathered. This documents *why* each thing matters and how to confirm it, so the
recorder can open the dongle cleanly.

Run the automated check anytime:

```bash
./scripts/preflight.sh
```

---

## 1. The v4 driver requirement

The **RTL-SDR Blog v4** uses an R828D tuner and **does not work with stock
librtlsdr** — you get no/garbage signal. It needs the
[`rtlsdrblog/rtl-sdr-blog`](https://github.com/rtlsdrblog/rtl-sdr-blog) driver
fork.

- **On the host:** you already built it — `rtl_test` / `rtl_eeprom` live in
  `/usr/local/bin`. Good.
- **In the container:** our image builds the same fork, so the v4 tunes
  correctly inside Docker. You do **not** need host RTL tools for the stack to
  run; they're just handy for testing.

Confirm the dongle is a v4 (Ctrl-C after a few seconds):

```bash
rtl_test -t
# expect:  "RTL-SDR Blog V4 Detected"
```

> `rtl_test` opens the dongle while it runs, so **Ctrl-C it before**
> `docker compose up`, or the container can't open the device.

---

## 2. Blacklist the DVB TV driver

When the kernel sees the dongle it may grab it with `dvb_usb_rtl28xxu` (it
thinks it's a TV tuner). That blocks SDR use. It must be blacklisted.

You already have it — three files under `/etc/modprobe.d/` blacklist
`dvb_usb_rtl28xxu`, and `lsmod` shows it isn't loaded. Verify:

```bash
lsmod | grep -E 'dvb|rtl28' || echo "not loaded (good)"
grep -rs rtl28xxu /etc/modprobe.d/
```

If it ever loads: `sudo rmmod dvb_usb_rtl28xxu` (and ensure a blacklist file
exists so it stays gone after reboot).

---

## 3. SDR contention — only one owner at a time

A given dongle can be opened by **exactly one** program. Right now **OpenWebRX
(`owrx`)** is using it (it's mapped to `/dev/bus/usb`). The recorder can't open
the dongle until owrx releases it:

```bash
docker stop owrx
```

`preflight.sh` lists any container mapped to `/dev/bus/usb` so you know what to
stop.

**Implication for the future:** to run live listening (OpenWebRX) *and* this
recorder at the same time, you need a **second dongle**. With one roof coax,
feed multiple dongles from a **powered multicoupler** (on the roadmap). Select
each dongle by **serial** so they don't get confused on a USB replug.

---

## 4. USB passthrough into Docker

The compose service uses the robust pattern (survives replug/re-enumeration):

```yaml
device_cgroup_rules:
  - 'c 189:* rwm'        # major 189 = USB character devices
volumes:
  - /dev/bus/usb:/dev/bus/usb
```

This mirrors how `owrx` already accesses the dongle, so it's known-good on this
host.

---

## Quick reference

| Check | Command | Want |
|---|---|---|
| Dongle on USB | `lsusb \| grep 0bda:2838` | one line |
| Is a v4 | `rtl_test -t` (Ctrl-C) | "RTL-SDR Blog V4 Detected" |
| DVB driver gone | `lsmod \| grep rtl28` | no output |
| Blacklisted | `grep -rs rtl28xxu /etc/modprobe.d/` | a match |
| Nothing holding it | `./scripts/preflight.sh` | "No running container…" |
