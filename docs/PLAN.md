# Cabin Hub — plan and status

Living document. Update it as work lands.
Requirements and device research: [CABIN_PROJECT_BRIEF.md](CABIN_PROJECT_BRIEF.md).
How to install and run: [DEPLOY.md](DEPLOY.md). Radio hardware: [RADIO.md](RADIO.md).

## Status (2026-10-31)

**All phases are built and tested in a container.** Nothing has run on the real
laptop or touched real devices yet. What's next needs Chris:

1. Run `scripts/inventory.sh` on the laptop and send the output.
2. Create the Cloudflare tunnel and run `scripts/install.sh` ([DEPLOY.md](DEPLOY.md) steps 3–6).
3. Add the TrackMix in the app and run the camera probe; send its output.

| Phase | State | Verified on real hardware? |
|---|---|---|
| 0 Host prep | Scripts + guide written | No — needs Chris |
| 1 Foundation (auth, roles, PWA, push, backups, health) | Built, tested | No |
| 2 Household (calendar, shopping, to-do) | Built, tested | n/a (no devices) |
| 3 Weather + Starlink | Built; tested with simulated Tempest packets | No — Tempest/Starlink [VERIFY] |
| 4 TrackMix | Built on `reolink_aio`; probe script ready | No — [VERIFY] streams, tele lens, PTZ, recordings, push events |
| 5 Argus | Skipped (decision) | — |
| 6 Radio | Built; generated config parses in RTLSDR-Airband | No — needs dongle; [VERIFY] filename/frequency format |

## Decisions

| # | Decision | Choice | Date |
|---|---|---|---|
| D1 | Stack | Python (FastAPI) + SvelteKit PWA + SQLite | 2026-10-31 |
| D2 | Argus Solar | Skip for now; keep using the Reolink app | 2026-10-31 |
| D3 | Remote access | Cloudflare Tunnel for everything, video included (risk accepted) | 2026-10-31 |
| D4 | Radio hardware | One dongle now; built so more dongles are added in the app | 2026-10-31 |
| D5 | P25 | Not planned | 2026-10-31 |
| D7 | Domain | hawksroost.live on Cloudflare DNS | 2026-10-31 |
| D8 | Roles | viewer / member / admin (see below) | 2026-10-31 |
| — | Bookings | Open booking; overlapping stays allowed but flagged | 2026-10-31 |
| — | Email | Brevo (SMTP), configured in the app | 2026-10-31 |
| — | Integrations | All set up in the admin UI, not in files. `.env` holds only the tunnel token and a few server options | 2026-10-31 |
| — | Git | Everything on `main`, no branches | 2026-10-31 |
| — | Build order | Radio last | 2026-10-31 |

**Roles**

| Can… | Viewer | Member | Admin |
|---|---|---|---|
| See everything, watch cameras, listen, download clips | ✓ | ✓ | ✓ |
| Book the cabin, edit lists, keep radio clips | | ✓ | ✓ |
| Pan/tilt the camera, go to presets | | ✓ | ✓ |
| Auto-tracking, settings, integrations, people, invites, others' bookings | | | ✓ |

**D3 mitigations:** sub-stream by default, full quality only on tap, live view
pauses after 5 minutes, no prefetching, video isolated under `/video/`.

## Decisions Claude made — for Chris to review

None of these block anything; each is easy to change.

1. **rdio-scanner and the separate "control service" from the old SDR plan are
   dropped.** The app's Radio tab does listening, recordings, Keep, retention and
   busy-channel alerts itself. One app, one login.
2. **Camera motion events use Reolink's TCP push (via `reolink_aio`)**, not the
   HTTP webhook. No camera-side webhook setup or LAN-only receiver needed. Falls
   back to polling every 3 s if push fails.
3. **Camera recordings stay on the SD card** for now (the brief's Phase 1). The
   recordings code sits behind one interface so a USB HDD can be added later.
4. **Secrets entered in the app (camera password, SMTP key, Google secret, Tempest
   token) are stored in the database unencrypted** and never sent back to the
   browser. The nightly backup (and the OneDrive copy) contains them. Encrypting
   them would need a key that also has to be backed up, so it buys little here.
5. **LAN access on port 8080 over plain HTTP** is on, for setup and for when
   Starlink is down. Notifications and install-as-app need HTTPS, so they only
   work through hawksroost.live.
6. **Default lists:** "To-do" and "Before we leave" (a reusable checklist with an "untick all" button).
7. **Times show in cabin time** (Arizona) for everyone, wherever they are.
8. **Weather data kept ~2 years; camera motion events 30 days; radio calls 30 days / 20 GB** (Keep and busy-channel calls never expire). All but weather are adjustable in the app.
9. **Login screen uses plain pine**, not a photo. The brand guide wants family photos; send some and they go in.
10. **Pine app icon generated** from the brand's transparent icon (the guide names `icon-cabin-512.png` but the package doesn't include it).
11. **Charts plot one series each.** The brand colours don't pass colour-blind
    separation as a multi-series palette, so temperature, wind, humidity, rain and
    Starlink latency each get their own chart.

## Still open

| Question | Needed by |
|---|---|
| Laptop inventory (OS, ports, existing nginx/OpenWebRX/Watchtower, LAN, Tempest/Starlink reachable) | Install |
| Who else is admin | Any time |
| Family photos for the login screen | Any time |
| Camera retention / when to add a USB HDD (D6) | After the camera runs a while |
| Verified radio channel list (RadioReference) | Radio |

## Architecture

```
 Family phones / PCs ──HTTPS──► Cloudflare ──tunnel (outbound only)──┐
                                                                     ▼
┌──────────────── Dell Latitude · Debian · Docker Compose ─────────────────────┐
│  cloudflared ──► web (nginx: app files; /api → api; /video → go2rtc;        │
│                       /radio/live → icecast; video+radio need a session)     │
│  api (FastAPI, 1 worker): auth, roles, push, calendar, lists, cameras,       │
│       radio indexer, nightly backup ── SQLite in data/                       │
│  collector (host network): Tempest UDP 50222, Starlink gRPC                  │
│  go2rtc: camera RTSP → MSE/HLS (streams registered by the api)               │
│  optional: offsite (rclone → OneDrive), airband + icecast (radio)            │
└───────────────────────────────────────────────────────────────────────────────┘
```

## Build log

- 2026-10-31 — Repo reorganised, old `sdr/` folder replaced by `docs/RADIO.md`.
- 2026-10-31 — Backend: auth, roles, settings-in-database, calendar, lists,
  collectors, cameras, radio, push, backups, probes. 24 tests pass.
- 2026-10-31 — Frontend: shell, sign-in, Today, Calendar, Lists, Cameras,
  Weather/Starlink, Radio, Settings, Admin (People, Integrations, Radio, Health).
  Checked at phone and desktop sizes, light and dark.
- 2026-10-31 — Full stack run in Docker here: nginx routes, auth guards on
  video/radio, simulated Tempest data, radio config accepted by RTLSDR-Airband
  (scan and multichannel), Icecast starts.
