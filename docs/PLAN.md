# Cabin Hub — plan and status

Living document. Update it as work lands.
Requirements and device research: [CABIN_PROJECT_BRIEF.md](CABIN_PROJECT_BRIEF.md).
How to install and run: [DEPLOY.md](DEPLOY.md). Radio hardware: [RADIO.md](RADIO.md).

## Status (2026-11-01, after the full review)

**Everything is built and running on the cabin laptop** at https://hawksroost.live:
Chris's admin account, the Reolink camera (live view, presets) and the radio
scanner (recording calls) are in use. The full code and design review (build log,
last entry) is pushed; it takes effect with `scripts/update.sh`. Items marked
[VERIFY] below can only be checked on the real devices.

| Area | State | Checked on real hardware? |
|---|---|---|
| Host prep, front door (Caddy + Let's Encrypt + DDNS) | Done | Yes |
| Sign-in, roles, PWA, push, backups, health, sign-in photo | Built, tested | Sign-in yes; iPhone notifications [VERIFY] after the review (push headers changed) |
| Calendar, Shopping, Lists | Built, tested | n/a |
| Weather + Starlink (own pages) | Built; tested with simulated data | [VERIFY] with the real station and dish |
| Cameras (Reolink, ONVIF, stream URL; live, PTZ, presets, recordings, clips, pictures, alerts, siren, light) | Built on drivers; clip cutting tested with a generated video | Live view, presets: yes. [VERIFY]: recordings playback, clips, push events, siren, light |
| Argus | Skipped (decision) | — |
| Radio (calls, live listening, tuning) | Built; Mormon Lake list in docs/RADIO.md | Recording: yes. [VERIFY]: live listening reconnecting after a retune |

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
| — | Email | Brevo, configured in the app. ~~SMTP~~ → **Brevo API: just an API key + send-from address** (Chris, 2026-11-01) | 2026-11-01 |
| — | Integrations | All set up in the admin UI, not in files. `.env` holds only the Cloudflare DNS token and a few server options | 2026-10-31 |
| — | Backups | Nightly local SQLite copies only; no off-site | 2026-10-31 |
| — | Git | Everything on `main`, no branches | 2026-10-31 |
| — | Build order | Radio last | 2026-10-31 |
| — | Devices | Phone, tablet and PC are all first-class: tabs on phones, icon rail on tablets, sidebar on computers | 2026-11-01 |
| — | Cameras | Brand-neutral: Reolink, ONVIF or a plain video URL; each camera says what it can do and the UI shows only that. No model names in the app | 2026-11-01 |
| — | Starlink | Own page. Only what the dish measures; usage counters and billing estimates removed | 2026-11-01 |
| — | Sign-in | No names on the page; Remember me, Forgot password, Request access | 2026-11-01 |
| — | Admin | Grouped by job: People, Site, Sign-in & email, Cameras, Weather, Starlink, Radio, System | 2026-11-01 |

**Roles**

| Can… | Viewer | Member | Admin |
|---|---|---|---|
| See everything, watch cameras, listen, download clips | ✓ | ✓ | ✓ |
| Book the cabin, edit lists, keep radio clips | | ✓ | ✓ |
| Pan/tilt the camera, go to presets, camera light | | ✓ | ✓ |
| Auto-tracking, siren, settings, integrations, people, invites, access requests, others' bookings | | | ✓ |

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
| Sign-in photo | Pine for now. **Added:** admin uploads a photo in Admin → Site |
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

## Claude's decisions for review (2026-11-01 redesign)

- **Remember me** is on by default. Off = cookie ends when the browser closes
  and the server ends the session after 24 hours without use.
- **Forgot password without email set up** notifies admins (push + email if
  available) so one can send a reset link from People. Same answer either way, so
  the page never reveals who has an account.
- **Request access** is rate-limited (5 an hour per address), ignores repeats and
  existing accounts, and notifies admins. Inviting from a request defaults the
  role to **viewer**; change it in the invite form if they should book or edit.
- **Camera siren** needs a second tap within 4 seconds; it sounds twice and stops
  (Reolink's default). Siren and auto-tracking are admin-only (Chris,
  2026-11-01); the light is a member-level on/off switch like pan/tilt.
- **ONVIF** cameras: main stream = the largest H.264 profile, sub = the smallest.
  Motion/person/vehicle/animal come from the camera's event topics, which vary by
  brand. [VERIFY] with a real ONVIF camera if one is ever added.
- **Weather 30-day view** shows one point per cabin day (low–high band + average);
  24 hours = 15-minute points; 7 days = 2-hour points.
- **Sea-level pressure** needs the station elevation (Admin → Weather). At 0 the
  app shows station pressure, labelled as such.
- **Starlink availability** = share of seconds where not every ping failed,
  counted only while the laptop was on.

- **Radio calls:** default join gap 10 s and minimum call 3 s (Chris's example).
  Joined calls have no silence between transmissions (shorter to listen to).
  A busy channel is still split into calls of at most 15 minutes. Incidents
  count transmissions, not calls. Deleting calls is admin-only.

- **Visits:** "Who's coming" starts with you ticked; the person who booked can
  still edit it even if they aren't going. Old delivery/repair entries stay
  on the calendar; new ones can't be made.
- **Weather icon without a forecast token:** sunny ≥ 75% of clear-sky sunlight,
  partly cloudy 40–75%, cloudy below; lightning within 20 km in 30 minutes
  shows a storm; rain at ≤ 0.5 °C shows snow.
- **Manual radio tuning** is a member control (like pan/tilt) and returns to
  scanning after 1 hour unless set otherwise, so fire calls aren't missed.

- **Full review (2026-11-01):**
  - **Push** now uses the standard VAPID header (RFC 8292) instead of the old
    draft one. Same keys, so devices stay subscribed. If iPhone notifications
    never arrived before, they may now [VERIFY].
  - **Signing out** turns off notifications on that device (it may be a shared
    tablet). A device that already has them on sends them to whoever signs in.
  - **Number settings** have limits, and a cleared box is refused rather than
    saved as 0: join gap 0–120 s, shortest call 0–120 s, storage 1–10,000 GB,
    keep calls 1–3,650 days, busy alert 2–500 calls in 1–240 minutes, quiet
    1–1,440 minutes, backup hour 0–23, backups kept 1–365 days, station
    elevation −1,000 to 15,000 ft, seconds between camera alerts 0–86,400.
  - **Live view** pauses after 5 minutes without a tap, click or key on the
    page (was 5 minutes regardless), so steering the camera never gets cut off.
  - **Shopping:** removing an item offers Undo for 6 seconds; Undo adds it back
    (it shows as newly added). Old delivery/repair entries can be deleted, not
    edited (editing turned them into visits).
  - **Admin → System:** optional things that aren't set up (email, Google) show
    a grey circle instead of counting as problems.
  - **Video:** the web server only passes our own camera streams to go2rtc;
    anything else in the address is refused (it could make go2rtc open any
    address on the cabin network).

## Still open

| Question | Needed by |
|---|---|
| Power-loss test (skipped by Chris 2026-10-31; Wake on AC set in BIOS, untested) | Optional |
| Camera probe output (now also siren/light support) | Camera |
| Listen-test Sheriff and Mormon Lake FD channels (may be P25 / unconfirmed) | Radio |
| Faster live view: set the camera's Fluent-stream I-frame interval to the smallest (DEPLOY.md, Cameras) [VERIFY setting name] | Camera |
| iPhone notifications after the push change; live listening coming back after a retune | After update |
| Delete old branches + set `main` default in GitHub | Any time (Chris) |

## Architecture

```
 Phones / tablets / PCs ──HTTPS──► hawksroost.live (DNS-only, kept current by ddns)
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
- 2026-11-01 — Redesign: works as well on tablets and PCs as phones; camera
  drivers (Reolink / ONVIF / stream URL) with capability-driven UI, siren and
  light; sign-in page with Remember me, Forgot password and Request access;
  Starlink's own page (status, alerts, sky map, live 15 minutes, history,
  reliability, latency under load, dish details, admin controls); Weather
  rebuilt (wind dial, rose, day/week/month charts to scale, daily table,
  derived dew point, feels-like, sea-level pressure); Admin split into eight
  sections with an overview. Fixed: weather history crashed (`range` shadowed
  Python's built-in), camera add/edit crashed reloading from a worker thread.
  Migration 0003. 41 tests pass.
- 2026-11-01 — Camera added on the laptop (Reolink; main admin login, Chris's
  choice). Live video didn't play: go2rtc refused the websocket because nginx
  sent `Host: go2rtc:1984` while the browser's Origin was hawksroost.live.
  nginx now passes the browser's host; reproduced and verified here against
  go2rtc 1.9.15 (signed in → 101, signed out → 401, other site → 403). Player
  now shows "Connecting…" until a picture arrives and offers a retry if none
  does. Added `scripts/camera-check.sh`.
- 2026-11-01 — Presets now follow the camera: re-read every 2 minutes and
  whenever a camera page is opened (at most every 15 s). Picture zoom in the
  player for every camera (pinch, Ctrl + scroll / trackpad pinch, + / −, drag,
  double-tap), tested in a browser with a stand-in video. The camera reports no
  camera-side zoom over its API (its "hybrid zoom" is the second lens plus
  digital cropping); the probe now prints its zoom fields to confirm.
- 2026-11-01 — Light is one on/off switch showing its real state; siren and
  auto-tracking are admin-only. Email switched from SMTP to Brevo's API
  (API key + send-from address only), checked against Brevo's OpenAPI spec;
  invites still work (link shown) if an email fails. 48 tests pass.
- 2026-11-01 — Brevo refused the first test: "unrecognised IP address"
  (its Authorised IPs protection). The app now says that in plain words and
  the System page shows "Last send failed" until a send works. Recommended:
  keep blocking on and allow the cabin's IP (Brevo API keys can do more than
  send mail); revisit if Starlink's address changes often.
- 2026-11-01 — Calendar: the month's bookings and Calendar apps sit to the
  right of the calendar on wide screens (stacked below 1150px). Shopping is
  its own page (`/shopping`); To-do and other lists stay at `/lists`
  (old `?tab=shopping` links redirect). Phones show five tabs + More.
- 2026-11-01 — Radio: transmissions on a channel within the join gap become
  one recording; calls under the minimum length aren't saved (both in Admin →
  Radio); admins can delete calls (migration 0004 adds `parts`). Tested with
  real MP3s made by ffmpeg. Camera recordings: play through the camera's
  Playback URL with Range passed through (Download fallback when it answers
  FLV), tested against a fake camera; "Full quality" looks up the matching
  main-stream file. 57 tests pass.
- 2026-11-01 — "To-do" page renamed Lists; Today has separate Shopping and
  Lists cards. Calendar: no delivery/repair option; visits have several
  people + "anyone else" (migration 0005 copies each booker in as coming).
  Weather icons on Weather and Today (station first, Tempest forecast, then
  sunlight vs clear sky). Radio: tune to one frequency (FM/AM, auto-return to
  scanning) or scan. 62 tests pass.
- 2026-11-01 — Full review (Chris asked for efficiency, bugs, cleanup, design
  and docs). Two independent reviews (backend, frontend), each finding checked
  before fixing, with tests:
  - **Speed:** live video starts in about 1–2 s here (player without go2rtc's
    overlay, sub-stream kept connected, player loaded while the page loads,
    camera list no longer waits on a slow camera); switching quality hangs up
    the old stream at once; radio live should start ~4 s behind instead of
    ~30 s (smaller Icecast burst, worked out from the recorder's bitrate;
    [VERIFY] by ear); history pages cached; gzip on the LAN.
  - **Bugs fixed:** making a clip always said "busy"; two clips of one
    recording clashed; a minute of Starlink data split across two polls kept
    only its second half; quick double saves left two camera connections
    running; cleared number settings saved as 0/blank (could empty backups or
    radio calls); pan/tilt Stop could overtake the move; a near-flat chart
    could freeze the Weather page; messages were hidden behind open forms;
    a dropped connection at start signed people out; stale answers showed
    under a newer selection; camera tiles stuck on Offline; radio sound didn't
    start on iPhones and stopped for good when the recorder restarted.
  - **Safety:** migrations run with foreign keys off (rebuilding a table could
    have deleted every row pointing at it, e.g. all bookings); video gate;
    security headers on every response; push requests time out.
  - **Cleanup:** unused routes, columns (migration 0006), helpers, CSS and a
    service-worker branch removed.
  - **Design:** Radio and Today use side-by-side columns on wide screens,
    tighter rows on Today, channels grouped with switches in Admin → Radio,
    44 px tap targets everywhere, notch-safe edges on tablets.
  - 72 backend tests pass (new: migrations match the models, push headers,
    settings limits, clip API, camera reload race, Starlink merge).
