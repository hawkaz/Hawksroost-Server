# CLAUDE.md — Hawksroost Cabin Hub

Private, invite-only PWA for the Hawk family cabin at Mormon Lake, AZ, used on
phones, tablets and computers alike: cabin calendar, shopping and to-do lists,
Tempest weather, Starlink, IP cameras, and (last) an SDR radio scanner. Runs on one laptop at the
cabin. Family scale, not production.

Read these before working:
- `docs/PLAN.md` — status, decisions, Claude's decisions for review, build log. **Keep it updated.**
- `docs/DEPLOY.md` — install/update/rollback/backup steps Chris follows on the laptop.
- `docs/CABIN_PROJECT_BRIEF.md` — requirements, acceptance criteria, device research.
- `branding/app-brand-guide.html` — the UI system (open in a browser; it's a JS bundle).

---

## Working with Chris

Chris is an IT director (Microsoft shop at work), ham operator, and home-automation
hobbyist. **He is technical but not a developer. Claude writes all code.** Chris
runs commands on the server and tests on his phone.

- Lead with the answer. No preamble about tone, honesty, or what kind of answer is coming.
- Brief, but include the detail needed to be correct and usable.
- Be frank. If an idea is bad, say so.
- Give steps as a short overview of the whole approach first, then **one step at a time**.
- **Never put an instruction for Chris and a question in the same message.**
- Ask clarifying questions when the answer would materially change the work.
- Don't fabricate. Mark anything unverified as **[VERIFY]**. Search before
  stating version- or product-specific facts.

### Commands Chris runs on the server (over SSH)

Every command must be **copy/paste ready**:
- Its own ```` ```bash ```` block, one command per block (a multi-line heredoc or
  `\` continuation stays one block). No `$` prompt, no output mixed in.
- No placeholders for him to fill in. If a value is secret or unknown, have him
  open `.env` with `nano` and give the exact line to add.
- Start with `cd /opt/hawksroost &&` (the repo's path on the server) or use absolute paths.
- The repo is **private**; the laptop pulls with a read-only deploy key (`github-hawksroost` SSH host alias).
- Say what it does, whether it needs `sudo`, and what success looks like.
- Anything longer than a couple of commands goes in a script under `scripts/`
  (`set -euo pipefail`, idempotent, prints clear `OK` / `FAIL` lines). Chris runs
  the script; he doesn't paste long sequences.
- Prefer read-only checks first. Warn before anything destructive.

Standard update after a push:
```bash
bash /opt/hawksroost/scripts/update.sh
```

---

## Stack (decided — see PLAN.md for dates)

| Piece | Choice |
|---|---|
| Host | Dell Latitude 5420, Debian 13 (hostname HAWKSROOST), Docker Compose. Nothing else runs in Docker (Home Assistant, Watchtower etc. retired). Pin third-party image tags; our services carry the Watchtower opt-out label in case it returns. |
| Backend | Python 3.12, FastAPI, SQLAlchemy 2 + Alembic, SQLite (WAL mode), pydantic-settings. **One uvicorn worker**: background jobs run in-process. |
| Frontend | SvelteKit **3** + Svelte 5 runes + TypeScript, `adapter-static` SPA (`200.html` fallback), plain CSS using brand tokens (no Tailwind or UI kits), `@lucide/svelte` icons, `@fontsource` latin subsets. Kit 3 notes: config lives in `vite.config.ts`; `$lib` is gone — import `#lib/...` **with the file extension** (`#lib/api.ts`, `#lib/session.svelte.ts`); service worker uses `$app/manifest` + `$app/environment`. |
| PWA | Manifest + service worker; Web Push with VAPID (`pywebpush`). iOS push needs Add to Home Screen (16.4+). |
| Email | Brevo transactional API (`mailer.py`, httpx): only an API key + send-from address in Admin → Sign-in & email; sender name = app name. |
| Auth | Invite-only. Google (OAuth code flow via httpx) or email/password (argon2). Server-side sessions in SQLite, cookie `HttpOnly; SameSite=Lax` (`Secure` over HTTPS). Roles `viewer` / `member` / `admin`. |
| Camera recordings | Played via the camera's Playback URL (Download if it answers FLV), proxied by the api with the browser's Range header passed through, as Home Assistant does; logs in again on an error page. "Full quality" finds the RecM file matching the RecS one [VERIFY]. |
| Cameras | Driver per camera kind in `services/cameras/drivers.py`: **reolink** (`reolink_aio`: PTZ, presets, auto-track, AI detections via TCP push, SD recordings, siren, light), **onvif** (`onvif-zeep-async`: streams, snapshot, PTZ, presets, pull-point motion/person events), **stream** (any RTSP/HTTP URL, view only). Each driver reports capabilities on connect; the API and UI only offer what a camera reports. No model names in the UI. go2rtc for RTSP → MSE/HLS; the api pushes streams through go2rtc's API. **go2rtc saves those streams, logins included, in `data/go2rtc/go2rtc.yaml`** (gitignored, never served). The camera records 24/7 to its SD card (set up in the camera's own app); the app only views it. Clips: the api fetches a recording over the LAN and cuts it with ffmpeg (`services/clips.py`, background job). |
| Weather | Tempest UDP broadcast on port 50222 (+ optional REST API). |
| Starlink | `starlink-grpc-core` against `192.168.100.1:9200`. Only what the dish measures: status, alerts, its own 15-minute stats, per-second history rolled up to minutes, sky obstruction map, sleep schedule; admin can reboot, stow, reset the map, set sleep. **No usage/data counters or billing estimates** (Chris: nothing that isn't accurate). Own page `/starlink`, not under Weather. |
| Radio | RTLSDR-Airband (+ Icecast for live listening). Config generated by the api from channels set in the app; the recorder restarts when it changes. The recorder writes one MP3 per transmission (UTC names; v5.2.0 has no hang-time or minimum-length option), so `radio_files.py` joins transmissions on a channel less than `join_gap_s` apart into one call in `recordings/calls/` (ffmpeg concat, no re-encode) and drops calls under `min_call_s`; both are admin settings. Admins can delete calls. |
| Remote access | **Direct.** Starlink Local Priority public IPv4 (bypass mode, Chris's own router forwards TCP 80/443 to 192.168.67.101). Caddy (host network) terminates HTTPS with automatic Let's Encrypt for `hawksroost.live` → app on :8080. `favonia/cloudflare-ddns` keeps DNS-only (grey cloud) records on the current IP. LAN: `http://<laptop>:8080`. |
| Backups | Nightly SQLite `.backup` into `data/backups` on the laptop. No off-site copy (Chris's choice). |

**Roles** (defined once in `backend/app/security.py` → `PERMISSIONS`):
viewer = see/listen/watch/download; member = also book, edit lists, keep radio
clips, pan/tilt/presets, camera light; admin = also auto-track, siren,
settings, integrations, people, invites, access requests, anyone's bookings. Check permissions with `deps.viewer /
member / camera_control / admin` on the API and `session.can(...)` in the UI.

**Video:** goes straight over Starlink (no Cloudflare proxy). Starlink upload is
limited, so keep video volume low: sub-stream by default, main stream only on
tap, live view auto-stops when idle, no prefetching. Video stays behind `/video/`.

---

## Conventions

- **Integration settings live in the database**, edited by admins in the UI
  (`settings_store.py`: one JSON section per integration; secret fields are
  write-only and come back as `<name>_set`). Add a new integration by adding a
  section there and a page under `routes/admin/` (listed in
  `lib/components/admin/sections.ts`). **Don't add
  integration settings to `.env`.** `.env` holds only the Cloudflare DNS token and a few
  server options. Never commit secrets, recordings, or `data/`.
- **Devices: probe before building.** Write a small probe script in
  `backend/probes/` for each integration, have Chris run it on the real hardware,
  and record results in `docs/probes/`. Never invent API commands, stream paths,
  or payload fields.
- **Integrations sit behind interfaces** (e.g. a recordings source that is the
  camera SD card now and local disk later) so the UI doesn't change. Cameras:
  add a new kind by writing a `Driver` subclass; anything it doesn't override
  raises `NotSupported` (→ 400 "This camera can't do that.").
- **Security:** only Caddy (80/443) faces the internet; it proxies to the app. The camera
  webhook receiver is plain HTTP on the LAN IP only. Never publish camera, go2rtc
  admin, Icecast admin, or SDR ports to the internet. Use a dedicated non-admin
  camera account where possible.
- **Time:** store UTC; display `America/Phoenix` (no DST).
- **Logs:** to stdout; every compose service sets `logging: max-size 10m, max-file 3`.
- **Health:** each integration reports to the health page (reachable, last data time).
- **Database:** Alembic migrations, applied automatically when `api` starts.
- **Tests before pushing:** `pytest` for backend logic (auth/invites, permissions,
  reservation overlap, list history); `npm run check` and `npm run build` for the
  frontend. Say plainly if something couldn't be tested here (most device work can't).
- **Keep it small:** no Kubernetes, message queues, extra databases, or new
  services without a clear reason. One `docker-compose.yml` at the root;
  optional services use profiles (`radio`) set in `.env` `COMPOSE_PROFILES`.
- **Testing here:** `cd backend && pytest`; `cd frontend && npm run check && npm run build`.
  For a full-stack check, Docker works in this container, but image builds need
  the sandbox CA injected via a *temporary copy* of the Dockerfile
  (`--build-context ca=/root/.ccr`); never add that to the real Dockerfiles.

---

## UI rules (from `branding/app-brand-guide.html`)

- **Tokens:** use the CSS tokens in section 09 of the guide exactly (`--pine`, `--copper`,
  semantic `--bg/--surface/--line/--text/--primary/--accent`, spacing `--space-1..8`,
  radius 4/6/12/999, one overlay shadow). Light and `[data-theme="dark"]` sets.
- **Type:** Bitter 600/800 for titles and headings; IBM Plex Sans 400/500/600 for UI;
  IBM Plex Mono for data (times, dates, quantities, frequencies). No other faces.
- **Theme:** follow `prefers-color-scheme`, allow a manual toggle; **force dark on
  Cameras and Radio**.
- **Shell:** one nav list (Today, Calendar, Shopping, To-do, Cameras, Weather,
  Starlink, Radio when on; then Settings, Admin). Phone <700px = pine top bar +
  bottom tabs (first five + More sheet). Tablet 700–899px = 80px icon rail. Desktop ≥900px =
  240px sidebar with full lockup. Content max-width 1120px. Lay pages out for all
  three (e.g. video beside controls on wide screens); never write phone-only copy.
- **Admin** is grouped by what you look after: `/admin` overview, then People
  (with access requests), Site, Sign-in & email, Cameras, Weather, Starlink,
  Radio, System (health + backups).
- **Sign-in page:** no personal names. Remember me (on = 120-day sliding
  session; off = browser-session cookie, 24 h server limit), Forgot password,
  Request access (notifies admins by push + email).
- **Size:** tap targets ≥44px; body text ≥15px on mobile.
- **Colour meaning:** red and pulsing only for live radio activity and alerts.
  Status colours only for meaning.
- **Cameras:** 16:9 tiles, name + timestamp on a bottom scrim.
- **Radio:** never autoplay; the user taps to listen.
- **Calendar:** events filled with the owner's family colour (8 options, per-person
  setting); logistics outlined; today copper-outlined.
- **Headings:** card and section titles are Bitter headings, not small-caps
  labels; keep `.label` for short data tags.
- **Logo:** inline the SVGs from `branding/logo/svg/`; never redraw the hawk or the
  state (`Mark.svelte`, `Lockup.svelte`). Below 32px use the hawk-only favicon.
  PWA icon = pine tile (`#2E4636`), theme-color `#2E4636`.
- **Charts:** one series per chart in `--accent` (brand colours fail CVD checks as
  a multi-series palette); `TimeChart` (line with optional low–high band, or bars;
  cabin-time axis, nice ticks, hover + table view). `WindDial`, `WindRose`,
  `ObstructionMap` for the special cases.
- **Voice:** like a note on the fridge. First names, sentence case, plain words.
  "Shed camera is offline since 3:10 pm." not "Error: stream unavailable (503)".
- No marketing pages, cookie banners, or footer boilerplate.

---

## Repo map

```
CLAUDE.md            this file
docker-compose.yml   the whole stack
.env.example         server options (Cloudflare DNS token, domains, LAN port, profiles)
docs/                PLAN.md, DEPLOY.md, RADIO.md, CABIN_PROJECT_BRIEF.md
branding/            app-brand-guide.html, logo/ (svg, png)
backend/app/         FastAPI: main.py, models.py, settings_store.py, security.py,
                     routers/ (one per area), services/ (cameras/ drivers, go2rtc, clips,
                     radio, jobs),
                     collector/ (Tempest, Starlink), cli.py
backend/migrations/  Alembic (runs on api start)
backend/probes/      device checks Chris runs on the laptop
backend/tests/       pytest
frontend/src/        routes/ (one folder per page), lib/ (api, session, format,
                     push, components), service-worker.ts, app.css (brand tokens)
frontend/nginx.conf  front door: routing + auth guard for video/radio
deploy/              Caddyfile (HTTPS front door), radio recorder wrapper, icecast image
scripts/             server-check, install, update, admin-invite, radio-on/preflight
data/                server-only runtime data (gitignored)
```

## Git

- **Everything goes to `main`. No branches** (Chris's rule).
- Clear commit messages. Don't open PRs unless Chris asks.
- Don't put model names or identifiers in commits or code.
