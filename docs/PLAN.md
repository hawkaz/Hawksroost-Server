# Cabin Hub — plan and status

Living document. Update it as work lands.
Requirements and device research: [CABIN_PROJECT_BRIEF.md](CABIN_PROJECT_BRIEF.md).
How to install and run: [DEPLOY.md](DEPLOY.md). Radio hardware: [RADIO.md](RADIO.md).

## Status (2026-10-31)

**All phases are built and tested in a container.** Nothing has run on the real
laptop or devices yet. Next needs Chris: deploy key + clone, then the laptop
survey with `scripts/server-check.sh`, then server prep ([DEPLOY.md](DEPLOY.md)).

| Phase | State | Verified on real hardware? |
|---|---|---|
| 0 Host prep | Scripts + guide written | No — needs Chris |
| 1 Foundation (auth, roles, PWA, push, backups, health, sign-in photo) | Built, tested | No |
| 2 Household (calendar, shopping, to-do) | Built, tested | n/a |
| 3 Weather + Starlink | Built; tested with simulated Tempest packets | No — [VERIFY] |
| 4 TrackMix (live, PTZ, recordings, clips, pictures, alerts) | Built on `reolink_aio`; clip cutting tested with a generated video | No — [VERIFY] streams, tele lens, PTZ, SD search/download, push events |
| 5 Argus | Skipped (decision) | — |
| 6 Radio | Built; researched Mormon Lake list (docs/RADIO.md) with repeater tones; generated config parses in RTLSDR-Airband | No — needs dongle |

## Decisions

| # | Decision | Choice | Date |
|---|---|---|---|
| D1 | Stack | Python (FastAPI) + SvelteKit PWA + SQLite | 2026-10-31 |
| D2 | Argus Solar | Skip for now; keep using the Reolink app | 2026-10-31 |
| D3 | Remote access | ~~Cloudflare Tunnel~~ → **direct**: Starlink Local Priority public IP, router forwards 80/443, Caddy + Let's Encrypt, Cloudflare DNS-only + DDNS updater. | 2026-10-31 |
| D4 | Radio hardware | One dongle now; built so more dongles are added in the app | 2026-10-31 |
| D5 | P25 | Not planned | 2026-10-31 |
| D7 | Domain | hawksroost.live on Cloudflare DNS | 2026-10-31 |
| D8 | Roles | viewer / member / admin (see below) | 2026-10-31 |
| — | Bookings | Open booking; overlapping stays allowed but flagged | 2026-10-31 |
| — | Email | Brevo (SMTP), configured in the app | 2026-10-31 |
| — | Integrations | All set up in the admin UI, not in files. `.env` holds only the Cloudflare DNS token and a few server options | 2026-10-31 |
| — | Backups | Nightly local SQLite copies only; no off-site | 2026-10-31 |
| — | Git | Everything on `main`, no branches | 2026-10-31 |
| — | Build order | Radio last | 2026-10-31 |

**Roles**

| Can… | Viewer | Member | Admin |
|---|---|---|---|
| See everything, watch cameras, listen, download clips | ✓ | ✓ | ✓ |
| Book the cabin, edit lists, keep radio clips | | ✓ | ✓ |
| Pan/tilt the camera, go to presets | | ✓ | ✓ |
| Auto-tracking, settings, integrations, people, invites, others' bookings | | | ✓ |

**Why D3 changed:** the brief assumed Starlink CGNAT. Chris has Local Priority
with a public IP, so a direct front door removes the Cloudflare video-policy
problem and the tunnel dependency. Starlink's public IP is reserved but not
static, hence the DDNS updater. Video volume is still kept low for Starlink's
upload: sub-stream default, full quality on tap, 5-minute live pause.

## Chris's answers (2026-10-31)

All 22 items answered on the decisions page. Recommended options were accepted
except where noted.

| Item | Answer |
|---|---|
| Radio UI | App's Radio tab only; no rdio-scanner |
| Camera motion events | Reolink TCP push. Chris manages the camera in the Reolink app; nobody else gets Reolink app access |
| Camera recordings | Camera records 24/7 to its SD card (configured in the Reolink app); retention = card size. The app is a viewer for those recordings. **Added:** save full-quality pictures, cut short clips from long recordings, save motion pictures |
| Secrets | Stored as-is in the database |
| Off-site backup | **None.** OneDrive backup removed; nightly local backups only |
| LAN access (:8080) | On |
| Starter lists | To-do + Before we leave |
| Times | Cabin time (MST, UTC−7, no DST) |
| Retention | Defaults |
| Sign-in photo | Pine for now. **Added:** admin uploads a photo in Admin → Integrations |
| App icon | Pine tile |
| Charts | One measurement per chart |
| Live view pause | 5 minutes |
| Booking notifications | On by default |
| Invite links | 7 days |
| Admins | Just Chris for now |
| Repo | Private → laptop uses a read-only deploy key (DEPLOY.md step 1) |
| Old branches | Claude to delete — **blocked by the session's safety check twice**; Chris deletes in GitHub and sets `main` as default (GitHub only allows that in settings) |
| Email sender | `cabin@hawksroost.live`, domain authenticated in Brevo |
| Host nginx | Not needed; left alone |
| OpenWebRX | Remove when the radio starts |
| Radio channels | Claude researches and verifies Mormon Lake fire/EMS, law, Forest Service; skip digital/encrypted/trunked |

## Laptop (survey 2026-10-31)

Dell Latitude 5420, Debian 13, i5-1145G7, 7.2 GB RAM, 256 GB NVMe (173 GB free).
Already good: battery charge limit 75–80%, lid ignored, sleep masked, unattended
upgrades on, watchdog on, Docker 26.1 + Compose v5 at boot, Starlink dish and
gRPC port reachable, RTL-SDR present. Found: time zone was Denver; ufw active
(blocked Tempest broadcasts); no low-battery shutdown; no Docker log limits;
old test recorder still running (20 GB); OpenWebRX, nginx-proxy-manager,
Portainer unused; Wi-Fi and Ethernet both on the same subnet; SSH password-only.

Chris's choices: remove nginx-proxy-manager, Portainer, OpenWebRX, old recorder,
and (later the same day) Home Assistant + Watchtower — not in use yet; Wi-Fi off; printing/Bluetooth/ModemManager
off; add an SSH key but keep password login. All in `scripts/server-prep.sh`.

## Still open

| Question | Needed by |
|---|---|
| Power-loss test (skipped by Chris 2026-10-31; Wake on AC set in BIOS, untested) | Optional |
| Camera probe output | Camera |
| Listen-test Sheriff and Mormon Lake FD channels (may be P25 / unconfirmed) | Radio |
| Delete old branches + set `main` default in GitHub | Any time (Chris) |

## Architecture

```
 Family phones / PCs ──HTTPS──► hawksroost.live (DNS-only, kept current by ddns)
                                  │  Starlink public IP → own router → TCP 80/443
┌──────────────── Dell Latitude · Debian · Docker Compose ─────────────────────┐
│  caddy (host network, Let's Encrypt) ──► web :8080 (nginx: app files;        │
│        /api → api; /video → go2rtc; /radio/live → icecast; session guard)    │
│  api (FastAPI, 1 worker): auth, roles, push, calendar, lists, cameras,       │
│       clips (ffmpeg), radio indexer, nightly backup ── SQLite in data/       │
│  collector (host network): Tempest UDP 50222, Starlink gRPC                  │
│  go2rtc: camera RTSP → MSE/HLS (streams registered by the api)               │
│  ddns: Cloudflare DNS records → current public IP                            │
│  optional: airband + icecast (radio)                                         │
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
- 2026-10-31 — Applied Chris's answers: removed OneDrive backup; sign-in photo
  upload; camera "Save picture", clips (fetch over LAN + ffmpeg cut, background
  job) and motion-picture download; deploy key flow for the private repo; Brevo
  domain steps; OpenWebRX removal step.
- 2026-10-31 — Researched Mormon Lake analog channels (32 loaded, 12 on by
  default, scan mode); added per-channel CTCSS tone (migration 0002).
- 2026-10-31 — Laptop prepared: survey, deploy key + clone to /opt/hawksroost,
  server-prep.sh run (all OK), UPower boot service verified after reboot,
  BIOS Wake on AC set. Power-loss test skipped.
- 2026-10-31 — Switched the front door from Cloudflare Tunnel to direct
  (Caddy + Let's Encrypt + Cloudflare DDNS) after Chris confirmed a Starlink
  public IP.
- 2026-10-31 — Retired Home Assistant and Watchtower (not in use yet); prep
  script removes them and the old ~/Docker stack.
