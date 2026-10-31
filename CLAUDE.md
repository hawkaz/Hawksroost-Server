# CLAUDE.md — Hawksroost Cabin Hub

Private, invite-only PWA for the Hawk family cabin at Mormon Lake, AZ:
cabin calendar, shopping and to-do lists, Tempest weather, Starlink status,
Reolink cameras, and (last) an SDR radio scanner. Runs on one laptop at the
cabin. Family scale, not production.

Read these before working:
- `docs/PLAN.md` — phases, decisions, open questions, current status. **Keep it updated.**
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
- Say what it does, whether it needs `sudo`, and what success looks like.
- Anything longer than a couple of commands goes in a script under `scripts/`
  (`set -euo pipefail`, idempotent, prints clear `OK` / `FAIL` lines). Chris runs
  the script; he doesn't paste long sequences.
- Prefer read-only checks first. Warn before anything destructive.

Standard update after a push:
```bash
cd /opt/hawksroost && git pull && docker compose up -d --build
```

---

## Stack (decided — see PLAN.md for dates)

| Piece | Choice |
|---|---|
| Host | Dell Latitude, Debian (hostname HAWKSROOST), Docker Compose. Watchtower runs on the host: put `com.centurylinklabs.watchtower.enable=false` on our services and pin third-party image tags. |
| Backend | Python 3.12, FastAPI, SQLAlchemy 2 + Alembic, SQLite (WAL mode), pydantic-settings. **One uvicorn worker**: background jobs run in-process. |
| Frontend | SvelteKit + TypeScript, `adapter-static` SPA, plain CSS using brand tokens (no Tailwind or UI kits), Lucide icons, fonts self-hosted (no Google Fonts call). |
| PWA | Manifest + service worker; Web Push with VAPID (`pywebpush`). iOS push needs Add to Home Screen (16.4+). |
| Auth | Invite-only. Google OIDC (Authlib) or email/password (argon2). Server-side sessions in SQLite, cookie `HttpOnly; Secure; SameSite=Lax`. Roles `admin` / `member`. |
| Cameras | `reolink_aio` for the TrackMix. go2rtc for RTSP → MSE/HLS. |
| Weather | Tempest UDP broadcast on port 50222 (+ optional REST API). |
| Starlink | `starlink-grpc-tools` against `192.168.100.1:9200`. |
| Radio (last) | RTLSDR-Airband + Icecast. Existing work in `sdr/`. |
| Remote access | Cloudflare Tunnel (`cloudflared`) at `https://hawksroost.live`. No inbound ports. |
| Backups | Nightly SQLite `.backup` + config → OneDrive via rclone. |

**Permissions:** members can view cameras, pan/tilt, and go to presets. Admin only:
auto-track toggle, editing presets, camera settings, invites, user management.

**Video over Cloudflare:** Chris accepted the risk that this conflicts with
Cloudflare's video policy. Keep video volume low: sub-stream by default, main
stream only on tap, live view auto-stops when idle, no prefetching. Keep all
video behind `/video/` so it can move to Tailscale later.

---

## Conventions

- **Config** lives in `.env` (gitignored), with every key documented in
  `.env.example`. Never commit secrets, recordings, or the database (`data/`).
- **Devices: probe before building.** Write a small probe script in
  `backend/probes/` for each integration, have Chris run it on the real hardware,
  and record results in `docs/probes/`. Never invent API commands, stream paths,
  or payload fields.
- **Integrations sit behind interfaces** (e.g. a recordings source that is the
  camera SD card now and local disk later) so the UI doesn't change.
- **Security:** only the `web` service is reachable through the tunnel. The camera
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
  services without a clear reason. One `docker-compose.yml` at the root
  (`sdr/` gets folded in during Phase 6).

---

## UI rules (from `branding/app-brand-guide.html`)

- **Tokens:** use the CSS tokens in section 09 of the guide exactly (`--pine`, `--copper`,
  semantic `--bg/--surface/--line/--text/--primary/--accent`, spacing `--space-1..8`,
  radius 4/6/12/999, one overlay shadow). Light and `[data-theme="dark"]` sets.
- **Type:** Bitter 600/800 for titles and headings; IBM Plex Sans 400/500/600 for UI;
  IBM Plex Mono for data (times, dates, quantities, frequencies). No other faces.
- **Theme:** follow `prefers-color-scheme`, allow a manual toggle; **force dark on
  Cameras and Radio**.
- **Shell:** mobile = pine top bar (mark + page title) + bottom tab bar
  (Today, Calendar, Lists, Cameras, Radio). Desktop ≥900px = 240px left sidebar with
  full lockup, content max-width 1120px. Radio tab hidden until Phase 6.
- **Size:** tap targets ≥44px; body text ≥15px on mobile.
- **Colour meaning:** red and pulsing only for live radio activity and alerts.
  Status colours only for meaning.
- **Cameras:** 16:9 tiles, name + timestamp on a bottom scrim.
- **Radio:** never autoplay; the user taps to listen.
- **Calendar:** events filled with the owner's family colour (8 options, per-person
  setting); logistics outlined; today copper-outlined.
- **Logo:** inline the SVGs from `branding/logo/svg/`; never redraw the hawk or the
  state. Below 32px use the hawk-only favicon. PWA icon = pine tile (`#2E4636`),
  theme-color `#2E4636`.
- **Voice:** like a note on the fridge. First names, sentence case, plain words.
  "Shed camera is offline since 3:10 pm." not "Error: stream unavailable (503)".
- No marketing pages, cookie banners, or footer boilerplate.

---

## Repo map

```
CLAUDE.md          this file
docs/              PLAN.md (status + decisions), CABIN_PROJECT_BRIEF.md, DEPLOY.md, probes/
branding/          app-brand-guide.html, logo/ (svg, png, logo brand-guide)
backend/           FastAPI app, migrations, tests, probes/          (Phase 1+)
frontend/          SvelteKit PWA                                    (Phase 1+)
deploy/            nginx config, backup job                         (Phase 1+)
scripts/           server helper scripts Chris runs                 (Phase 0+)
sdr/               earlier SDR work (RTLSDR-Airband); reworked in Phase 6
data/              server-only runtime data (gitignored)
```

## Git

- Work on the branch the session assigns; never push elsewhere without asking.
- Clear commit messages. Don't open PRs unless Chris asks.
- Don't put model names or identifiers in commits or code.
