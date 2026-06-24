# Step 1 — Verify recording (NOAA 162.400)

**Goal:** prove the receive → demodulate → record chain works by capturing the
NOAA WXK76 continuous carrier (162.400 MHz, Mt. Eldon) to `.mp3` files. Once
files land, we move on to rdio-scanner (Step 2).

## Procedure (on the cabin host)

```bash
# 0) Get this branch onto HAWKSROOST
git pull

# 1) Preflight — dongle present, blacklisted, and not held by another app
./scripts/preflight.sh

# 2) Free the SDR — OpenWebRX currently owns it
docker stop owrx

# 3) Environment (sets TZ for filename timestamps)
cp .env.example .env

# 4) Start just the recorder
docker compose up -d rtlsdr-airband

# 5) Watch it come up
docker compose logs -f rtlsdr-airband

# 6) Confirm files are landing (new shell, or after Ctrl-C on the logs)
./scripts/verify-recording.sh
ls -lh recordings/
```

## What success looks like

- **Logs** show the device opening and tuning — e.g. `Found Rafael Micro R828D
  tuner`, `RTL-SDR Blog V4 Detected`, `RTLSDR device 0 initialized`, then
  `Writing to /recordings/NOAA_162.400_…` — with no repeating fatal errors.
- **A file appears and grows:** while recording, the in-progress file is named
  **`NOAA_162.400_YYYYMMDD_HH.mp3.tmp`** (note the `.tmp`). RTLSDR-Airband
  renames it to the final **`.mp3`** only when the file closes — at the **top of
  the hour** for NOAA's continuous carrier (or per-transmission on squelch-gated
  channels). A steadily growing `.tmp` is exactly right. (This `.tmp` → `.mp3`
  rename is also what lets Step 2's dirwatch avoid ingesting half-written files.)
- **It plays** and you hear the NWS weather broadcast (the computerized voice).
  This host has no audio out and no `ffplay`, so copy it to a machine that does
  — a partial `.tmp` is a valid MP3 and plays fine:

  ```bash
  # from your laptop, on the same LAN:
  scp 'chris@<host-ip>:~/hawksroost-server/recordings/NOAA_162.400_*.mp3.tmp' .
  # (optional) analyze on the host instead: sudo apt install -y ffmpeg
  #   ffprobe recordings/NOAA_162.400_*.mp3.tmp        # shows a valid audio stream
  ```

> Filenames use **local time** (`localtime = true` + `TZ=America/Phoenix`).

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Container restarts in a loop | SDR is busy or not found | `docker stop owrx`; re-run `./scripts/preflight.sh` |
| `usb_open error -3` / can't claim | another program holds the dongle | stop owrx / `rtl_test` / any SDR app |
| Device not found / no RTL device | dongle unplugged, or `dvb_usb_rtl28xxu` loaded | check `lsusb`; `sudo rmmod dvb_usb_rtl28xxu` |
| Runs, but **no file** after ~1 min | wrong `directory`, or bind mount | confirm `./recordings` exists; check logs for the output path |
| File exists but **silent / static** | gain too low/high, or weak off-band antenna | edit `gain` in `rtl_airband.conf` (try 20 → 35), `docker compose restart rtlsdr-airband` |
| Audio distorted / clipping | gain too high (overload) | lower `gain` (e.g. 28 → 20) and restart |
| Garbage even at sane gain | not using the v4 driver | confirm image pulled OK; `rtl_test -t` shows "V4 Detected" |

### Tuning gain
Edit `rtlsdr-airband/rtl_airband.conf` → `gain` (dB, ~0–49.6). NOAA is strong,
but your roof **GP-6 is off-band at 162 MHz**, so you may need more than a tuned
antenna would. Change one value, then:

```bash
docker compose restart rtlsdr-airband
```

### If 162.400 is weak at the cabin
Other NOAA frequencies sit in the same ~2 MHz window. Uncomment one of the
extra NOAA channel blocks in `rtl_airband.conf` (162.550, 162.475, …) and
restart — parallel monitoring is free, so you can run several and keep whichever
is strongest.

## When this works

Tell me and we proceed to **Step 2 (rdio-scanner dirwatch)**. We'll likely also
re-park this single dongle from NOAA onto your **forestry/fire sub-window** (the
real incident channels) once you've verified those freqs on RadioReference —
see [band-planning.md](band-planning.md) and [channel-plan.md](channel-plan.md).
