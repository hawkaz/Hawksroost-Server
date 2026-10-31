# Cabin Hub — build plan

Living document. Update it as phases complete and decisions change.
Requirements and device research: [CABIN_PROJECT_BRIEF.md](CABIN_PROJECT_BRIEF.md).
UI system: [../branding/app-brand-guide.html](../branding/app-brand-guide.html).

**Current status:** planning done → next is **Phase 0 (host prep)**.

---

## What we're building

A private, invite-only PWA at **https://hawksroost.live** for family and friends:

| Area | What people get | Phase |
|---|---|---|
| Sign-in | Invite-only; Google or email/password; admin + member roles | 1 |
| Alerts | Web Push to installed PWA, per-user camera/detection prefs, mute | 1 (plumbing), 4 (camera alerts) |
| Calendar | Book the cabin by date range; overlap check; iCal feed | 2 |
| Lists | Shopping list and project/to-do list with who/when history | 2 |
| Weather | Tempest live conditions + history, lightning, rain | 3 |
| Starlink | Online/latency/obstruction, approximate data usage | 3 |
| Cameras | TrackMix live (wide + tele), PTZ, presets, recordings, download | 4 |
| Argus | Depends on decision D2 | 5 |
| Radio | Scan + record, recordings browser, live listen | 6 (last) |

Out of scope: subscriptions, cloud NVR, Kubernetes, anything that needs more
than one laptop.

---

## Decisions

| # | Decision | Choice | Date |
|---|---|---|---|
| D1 | Stack | **Python (FastAPI) + SvelteKit PWA + SQLite** | 2026-10-31 |
| D3 | Remote access | **Cloudflare Tunnel for everything, video included** | 2026-10-31 |
| D7 | Domain | **hawksroost.live**, DNS on Cloudflare | 2026-10-31 |
| D8 | Camera permissions | Members: view, pan/tilt, go to preset. Admin only: auto-track toggle, edit presets, camera settings | 2026-10-31 |
| — | Build order | SDR is the **last** phase | 2026-10-31 |
| — | Radio UI | The app's Radio tab replaces rdio-scanner; radio alerts use the app's Web Push (not ntfy) | 2026-10-31 (proposed, confirm in Phase 6) |
| — | Location | Mormon Lake, AZ (Coconino County) | — |

**D3 risk, accepted:** Cloudflare's docs say video over Tunnel public hostnames on
free plans falls under their no-video-streaming policy. Chris chose this for
zero-install family access. Mitigations built in:
- Sub-stream (lower resolution) by default; main/4K stream only on tap.
- Live view auto-stops after a few minutes without interaction.
- Recordings are downloaded on demand, never pre-fetched.
- Video path is isolated (go2rtc behind `/video/`), so it can move to Tailscale
  later without touching the rest of the app.

### Still open (decided when the phase that needs them starts)

| # | Question | Needed by |
|---|---|---|
| — | Host inventory: Debian version, existing containers (OpenWebRX, Watchtower, nginx / nginx-proxy-manager), LAN subnet, Tempest hub on same subnet, Starlink dish reachable at 192.168.100.1 | Phase 0 |
| — | Is the existing nginx needed in front of the app, or can it be retired / left alone? | Phase 0 |
| — | Which branch the server tracks (repo has no `main` yet) | Phase 0 |
| — | Who the admins are | Phase 1 |
| — | Family photos for the login screen and empty states (brand guide) | Any time; pine colour until then |
| — | Reservations: first-come or needs admin approval? Overlap blocked or just flagged? | Phase 2 |
| D2 | Argus Solar: Reolink app only / Home Hub / experimental `reolink_aio` / return it | Phase 5 |
| D6 | Camera retention; when to add a USB HDD and record on the laptop | Phase 4 |
| D4 | Buy a second RTL-SDR for live listening while scanning | Phase 6 |
| D5 | P25 needed? Final channel list (verify on RadioReference) | Phase 6 |

---

## Architecture

```
 Family phones / PCs ──HTTPS──► Cloudflare ──tunnel (outbound only)──┐
                                                                     │
┌──────────────── Dell Latitude · Debian · Docker Compose ───────────┼────────┐
│                                                                    ▼        │
│  cloudflared ──► web (nginx: SvelteKit build, proxies /api, /video)         │
│                     ├─► api (FastAPI, 1 worker)                             │
│                     │     ├─ SQLite (data/hawksroost.db)                    │
│                     │     ├─ auth, invites, sessions, Web Push              │
│                     │     ├─ calendar, lists                                │
│                     │     ├─ cameras: reolink_aio → TrackMix (LAN)          │
│                     │     └─ reads collector + radio data                   │
│                     └─► go2rtc (RTSP from TrackMix → MSE/HLS)               │
│                                                                             │
│  collector (host network): Tempest UDP 50222 · Starlink gRPC poll           │
│  camera-hook (LAN-only plain HTTP): TrackMix motion webhook → api           │
│  backup (nightly): SQLite + config → OneDrive via rclone                    │
│  sdr/* (Phase 6): rtl_airband + icecast                                     │
└─────────────────────────────────────────────────────────────────────────────┘
```

Notes:
- **No inbound ports** on the router. Only `web` is reachable through the tunnel.
- The **camera webhook** must be plain HTTP (Reolink can't push to HTTPS), so
  it listens on the laptop's LAN IP only and is never routed through Cloudflare.
- **Tempest** broadcasts UDP on the LAN; Docker port publishing is unreliable
  for broadcasts, so the collector uses host networking. [VERIFY on host]
- **Starlink** gRPC at `192.168.100.1:9200` must be reachable from the laptop.
  [VERIFY on host]
- **Single API worker** on purpose: background jobs (push, polling, cleanup)
  run inside it, and more workers would duplicate them.

---

## Repo layout

Current (✓) and planned (Phase N):

```
.
├── CLAUDE.md                 ✓ rules for Claude: stack, conventions, how to work with Chris
├── README.md                 ✓ overview + server quick reference
├── docs/
│   ├── CABIN_PROJECT_BRIEF.md ✓ requirements + device research (source)
│   ├── PLAN.md               ✓ this file
│   ├── DEPLOY.md               Phase 0: first install, update, rollback, rebuild-from-backup
│   └── probes/                 Phase 3-5: results of device probe scripts
├── branding/                 ✓ brand guides + logo SVG/PNG (source of truth for UI)
├── docker-compose.yml          Phase 1
├── .env.example                Phase 1 (every setting documented)
├── scripts/                    Phase 0+: server helper scripts Chris runs
├── backend/                    Phase 1: FastAPI app, Alembic, tests, probes/
├── frontend/                   Phase 1: SvelteKit PWA
├── deploy/                     Phase 1: nginx config, cloudflared notes, backup job
├── data/                       on server only (gitignored): DB, snapshots, backups
└── sdr/                      ✓ earlier SDR work, reworked in Phase 6
```

---

## Phases

Each phase ends with something working on the laptop that Chris can test from
his phone. A phase isn't done until its checklist passes on the real hardware.

### Phase 0 — Host prep (no app code)
- Inventory the laptop with one read-only script (OS, disk, Docker version,
  running containers, ports in use, LAN subnet, Tempest packets seen,
  Starlink reachable).
- Dell BIOS: set battery charge limit (Primarily AC / custom 50–80%).
- Clone the repo to `/opt/hawksroost`.
- Cloudflare: create the tunnel for `hawksroost.live`, store its token in `.env`.
- Google Cloud: create the OAuth client (redirect `https://hawksroost.live/api/auth/google/callback`).
- Generate VAPID keys and the app secret (script).

**Done when:** inventory reviewed, repo cloned, tunnel token and OAuth client in `.env`.

### Phase 1 — Foundation
- Compose stack: `web`, `api`, `cloudflared`, `backup`. Log rotation on every service.
- App shell per brand guide: pine top bar + bottom tabs (mobile), 240px sidebar
  (desktop ≥900px), light/dark with manual toggle. Radio tab hidden until Phase 6.
- Auth: invites (admin creates, link expires), Google or password sign-up,
  sessions, roles. First admin created by a one-time server command.
- PWA: manifest, pine icon tile (generated from `branding/logo/svg/icon-transparent.svg`
  on `#2E4636`), service worker, offline shell, install prompts (iOS instructions).
- Web Push: subscribe per device, admin "send test notification".
- Health page: each integration's status.
- Nightly backup to OneDrive via rclone.

**Done when:** Chris installs the PWA on his phone over hawksroost.live, signs
in with Google, invites a second person who signs up with a password, and both
get a test push.

### Phase 2 — Household
- Calendar: month/week views, book a date range, overlap check, per-person
  family colour, logistics events (outlined), iCal feed per user.
- Shopping list: add (who/when), mark acquired (who/when), history, optional
  quantity and store group ("Flagstaff run").
- To-do/projects: same pattern + priority, notes, assignee.
- Today screen: next booking, open to-dos, shopping count.

**Done when:** two people can book, collide, add and tick items from phones, and
history shows who did what.

### Phase 3 — Weather and Starlink
- Probe scripts: capture Tempest UDP packets; call Starlink `get_status` /
  `get_history`. Record results in `docs/probes/`.
- Collector: store Tempest observations and Starlink samples; integrate
  throughput into daily and billing-cycle usage (labelled approximate).
- Weather page + Today card: current, 24h/7d charts, rain, lightning, wind.
- Starlink card: online, latency, obstruction, usage.

**Done when:** values match the Tempest app and Starlink app within reason, and
survive a container restart.

### Phase 4 — TrackMix camera
- **Probe first**: login, stream paths for both lenses, PTZ, presets,
  auto-track get/set, recording search/download, webhook delivery, dedicated
  non-admin camera user. Only build on what the probe confirms.
- go2rtc live view (sub-stream default, main on tap, idle auto-stop).
- PTZ pad + presets (members); auto-track toggle and preset edit (admin).
- Recordings browser by date/time from the SD card; play; download MP4.
- Motion alerts: webhook → event log + snapshot → Web Push per user prefs
  (camera, detection type), per-camera cooldown, mute until.

**Done when:** live view works over cellular, PTZ moves the camera, a recording
downloads, and walking past the camera pushes an alert only to people who
opted in.

### Phase 5 — Argus Solar
Per decision D2. Nothing built until that's chosen.

### Phase 6 — Radio (last)
Carry over from `sdr/` (already working or specced there):
- RTLSDR-Airband on the V4 dongle (V4 driver, preflight, Watchtower opt-out).
- One file per transmission, tagged with frequency/label/time.
- Channel groups (Fire, EMS, Sheriff, Forest Service) from a verified channel list.
- NVR-style retention: size cap + age backstop, **Keep** flag protects clips.
- Incident detection on `incident: true` channels → Web Push alert, auto-Keep.
- Frequency admin page (validated against the dongle's ~2 MHz window).

New for the app:
- Radio tab: scanner status, red/pulsing only while a channel transmits,
  recordings list filterable by channel/date, player. Never autoplays.
- Live listen via Icecast; scanning vs live tuning depends on D4.
- P25 only if D5 says so.

### Phase 7 — Later
- USB HDD + record RTSP on the laptop behind the same recordings interface.
- Extra cameras, more Starlink history, etc.

---

## Deployment workflow (how updates reach the laptop)

1. Claude commits and pushes to GitHub.
2. Chris runs, over SSH on the laptop:
   ```bash
   cd /opt/hawksroost && git pull && docker compose up -d --build
   ```
3. Claude says what to check and what success looks like.

Rollback, first install, and rebuilding from a backup go in `docs/DEPLOY.md`
(Phase 0).
