# Cabin Hub — Project Brief for Claude Code

Owner: Chris (IT director; ham radio and home-automation hobbyist; Microsoft shop at work)
Prepared: 2026-10-30
Status: Requirements and research done. Next: finish planning with Chris, then build in phases.

---

## 0. How to use this brief (read first)

1. **Start in plan mode.** Read this whole file, then resolve the **Open Decisions** (section 9) with Chris before writing code.
2. **Treat device APIs as unverified until tested on the real hardware.** Items marked **[VERIFY]** came from forum posts, retailer pages, or memory, not from testing. Write a small probe script for each integration and confirm it before building UI on top of it.
3. **Don't invent API commands, stream paths, or payload fields.** If something isn't confirmed here or by a probe against the device, say so and test it.
4. **Working style Chris wants:**
   - Lead with the answer. No preamble about tone or honesty.
   - Brief, but include the detail needed to be correct.
   - Be frank. If an idea is bad, say so.
   - When giving steps: give a short overview of the whole approach first, then **one step at a time**.
   - **Never combine an instruction for Chris with a question in the same message.** Ask the question by itself, or give the step by itself.
   - Ask clarifying questions when the answer would materially change the work.
5. Once decisions are made, generate a `CLAUDE.md` for the repo that captures the stack, conventions, and these working-style rules.

---

## 1. Goal

A self-hosted, invite-only web app (installable PWA) for a family cabin in northern Arizona. It combines:
- security and wildlife cameras
- a police/fire/EMS/Forest Service radio scanner
- weather
- Starlink status
- cabin logistics: reservations, shopping list, to-do list

**Hard constraints**
- **No subscriptions** for cameras, storage, or services.
- **Everything runs on-site** on one laptop.
- **Family scale, not production.** Keep it simple and maintainable by one person. Avoid Kubernetes, microservice sprawl, and paid SaaS.

---

## 2. Hardware and site inventory

| Item | Details | Notes |
|---|---|---|
| Server | Dell Latitude laptop, always on, Debian, Docker installed | Single point of failure. Battery doubles as a short UPS. Set the Dell BIOS charge limit to avoid battery swelling from always-on charging. |
| Internet | Starlink (residential) | Assume carrier-grade NAT: no inbound ports. Upload bandwidth is limited and variable. |
| Camera 1 | **Reolink TrackMix PoE** (also sold as TrackMix Series P760) | Dual lens: 2.8mm wide (4K) + 8mm telephoto (1080p / 2MP). Pan/tilt, auto-tracking (person/vehicle/animal). PoE 802.3af. microSD slot. 10/100 Ethernet. |
| Camera 2 | **Reolink Argus Solar** (3K 5MP, WiFi 6, battery + solar) | **Battery camera. See section 4.2: no RTSP/ONVIF/API when standalone.** Intended only for motion recording. |
| Weather | Tempest weather station + hub | Hub on the same LAN as the laptop (confirm). |
| Radio | RTL-SDR Blog V4 (one dongle today) | A second dongle is likely needed (section 4.4). |
| Network | PoE cable/switch available for the TrackMix | Confirm the PoE switch is 802.3af active (48V). |

**Recording plan:** start with microSD in each camera. Possibly add an external USB HDD on the laptop later for longer retention.

---

## 3. Requirements and acceptance criteria

| # | Requirement | Acceptance criteria |
|---|---|---|
| 1 | Login: invite-only, Google sign-in **or** email/password | No open registration. An admin creates an invite; the invitee signs up with Google or a password. Roles: admin and member. |
| 2 | View and control cameras (live and recordings) | **TrackMix:** live wide and telephoto views; pan/tilt; go to preset; toggle auto-tracking; browse recordings by date and time and play them. **Argus:** depends on decision D2. |
| 3 | Download recordings | User can download a clip as a file (MP4). |
| 4 | Motion alerts to phone, per-user setting | Web Push to the installed PWA. Each user picks which cameras and which detection types (person/vehicle/animal/motion). Cooldown or rate limit per camera. |
| 5 | Mute alerts for a period | Per-user "mute until" (e.g., 1h, 8h, until date). Optionally a per-camera mute. |
| 6 | Cabin reservation calendar | Users reserve date ranges; overlapping reservations are blocked or flagged. Nice to have: read-only iCal feed per user. |
| 7 | Shopping list | Add an item (record who and when); mark acquired (record who and when); show history. |
| 8 | To-do and project list | Same pattern as #7. Optional fields: priority, notes, assignee. |
| 9 | Live SDR audio with preset channels | Listen in the browser; choose from preset channel groups (Fire, EMS, Sheriff, Forest Service). |
| 10 | SDR scans and records on traffic | One recording file per transmission, tagged with frequency, label, and timestamp. |
| 11 | Listen to SDR recordings in the app | Filterable list by channel and date, with playback. |
| 12 | Tempest weather data | Current conditions plus recent history; lightning and rain events if available. |
| 13 | Starlink connection and data usage | Online/offline, latency, obstruction, throughput; cumulative bytes per day and per billing cycle (approximate). |

---

## 4. Research findings and constraints

### 4.1 Reolink TrackMix PoE

- **HTTP API:** JSON over HTTP POST to `/cgi-bin/api.cgi?cmd=<Command>&token=<token>`. Log in first with `cmd=Login` to get a token.
- **Commands seen in the wild:**
  - Recordings: `Login`, `Search`, `Download`, `Logout`. A user reports Login → Search → Download works on both a TrackMix PoE and a TrackMix WiFi for pulling SD-card recordings. (The same flow failed on an RLC-823S2, so behavior varies by model; test on the actual unit.)
  - PTZ: `PtzCtrl` (example: `{"channel":0,"op":"ToPos","id":2,"speed":32}` to go to a preset), `GetPtzPreset`.
  - Auto-tracking: `GetAutoTrack` and `SetAutoTrack`.
  - Snapshots: `Snap`. **[VERIFY]**
- **Python library:** `reolink_aio` (pip), officially authorized by Reolink and used by Home Assistant. It covers the API, ONVIF event subscription to a webhook, and Reolink's TCP push events. **Prefer it over hand-rolled calls if the backend is Python.**
- **Webhook (motion → HTTP POST):**
  - Officially supported on TrackMix PoE hardware `IPC_529SD78MP` with current firmware. Reolink calls it a test feature; configure it in the camera's **web UI** under Settings > Surveillance > Push > Webhook.
  - **Only works when the camera is standalone (not attached to a Reolink NVR or Home Hub).** Keep the TrackMix standalone.
  - Sends HTTP POST only, `Content-Type: application/json`. The default body looks like this; a custom body is limited to 750 bytes of JSON:
    ```json
    {"alarm":{"alarmTime":"…","channel":"…","channelName":"…","device":"…","deviceModel":"…","message":"…","name":"…","time":"…","type":"…"},"secret":"…","type":"…"}
    ```
  - Home Assistant's code notes that Reolink devices **can't push events to HTTPS**. Expose a **plain-HTTP, LAN-only** receiver endpoint for camera events, separate from the public HTTPS app.
- **Streams:**
  - RTSP main/sub paths like `rtsp://user:pass@IP:554/h264Preview_01_main` and `/Preview_01_sub` are common on Reolink cameras. **[VERIFY]** the exact paths for the wide and telephoto lenses on this unit. Via ONVIF, stream 2 has been reported as the zoom lens and stream 3 as the tracking zoom. Enumerate profiles with an ONVIF probe.
  - Set encoding to **H.264** if browser playback of H.265 is a problem.
- **Image facts:**
  - Telephoto is 1080p at about a 38° horizontal field of view. "6x hybrid zoom" is the lens switch at about 2.7x, then digital cropping.
  - Operating range is reported as −10°C to +55°C. Northern AZ winter nights can go below that; monitor for cold-weather issues.
- **Tracking:** auto-tracking runs on the camera. The app only toggles it and sets presets and the guard position; don't build server-side tracking.

### 4.2 Reolink Argus Solar (battery camera) — integration blocker

- **Standalone, it has no RTSP, RTMP, or ONVIF.** Reolink says to use their software. It's also not on the webhook support list.
- **With a Reolink Home Hub, battery cameras gain third-party protocols.** Hub compatibility varies by model; check the specific Argus model against Reolink's Home Hub compatibility list. **[VERIFY]**
- **Home Assistant 2026.6** added *initial* direct support for battery cameras via a new protocol in `reolink_aio`. The developer says not everything works yet and still recommends a Hub. Live streaming isn't implemented because these cameras use a proprietary streaming protocol.
- **See decision D2.** Webhooks don't work behind a Hub. If the Argus goes on a Hub, get its events through `reolink_aio` (ONVIF or TCP push subscription to the Hub) instead.

### 4.3 Recording and storage

- **Phase 1:** 24/7 recording to the TrackMix microSD; the app indexes and downloads via `Search` and `Download`.
- **Known weaknesses of SD-only recording:**
  - Cards wear out under 24/7 4K writes.
  - Retention is short.
  - Footage is lost if the camera is stolen.
  - The SD index can lag.
- **Later:** add a USB HDD and record RTSP on the laptop (ffmpeg segmenter, or Frigate/Blue Iris-style recorder). Design the recordings module behind an interface so the source can switch from "camera SD" to "local disk" without UI changes.
- **Rough storage math (assumed bitrates — [VERIFY] actual camera settings):** about 6 Mbps for 4K plus about 3 Mbps for 1080p is about 9 Mbps, roughly 97 GB/day or 2.9 TB per 30 days for the TrackMix if recorded continuously on the laptop.

### 4.4 SDR (RTL-SDR V4)

**Assumed location: near Flagstaff. [VERIFY]** cabin location and current frequencies with Chris (he's a ham) and RadioReference before configuring.

Starting channel list, from a Broadcastify feed description (may be outdated):

| Group | Label | Frequency (MHz) | Mode |
|---|---|---|---|
| Sheriff | CCSO-1 Sheriff (Flagstaff) | 155.490 | Analog. One RadioReference post reports a move to P25 on "2 Adam". **[VERIFY]** |
| Sheriff | CCSO-2 Dispatch | 155.835 | Analog **[VERIFY]** |
| Fire/EMS | Highlands Dispatch | 154.175 | Analog |
| Fire/EMS | Pinewood Dispatch / Ops | 154.190 / 154.235 | Analog |
| Fire/EMS | Ponderosa Dispatch | 154.430 | Analog |
| Forest Service | Coconino North | 171.425 | Analog |
| Forest Service | Coconino South | 172.300 | Analog |
| City Fire/PD | Flagstaff | P25 talkgroups | Digital (needs P25 decoder; may be encrypted) |

**Constraints**
- One RTL-SDR covers about 2.5 MHz. These channels span about 18 MHz, so one dongle **must scan** (hop between frequencies) and will miss simultaneous traffic.
- **RTLSDR-Airband:**
  - Has a **scan mode** that hops between arbitrary frequencies and outputs a single audio stream.
  - Can **write a separate file per transmission** (`split_on_transmission` / per-transmission output; check the docs for the installed version).
  - Can stream MP3 to **Icecast**.
  - Decodes **AM and NFM only**, so no P25.
- **P25:** needs SDRTrunk or OP25 if required. Encrypted talkgroups can't be monitored, by design and by law.
- **Live retuning conflicts with scanning on a single dongle.** Recommend dongle #1 for scan-and-record and dongle #2 for live listening (decision D4).

### 4.5 Tempest

- The hub broadcasts JSON over **UDP port 50222** on the local subnet; no auth or configuration needed. Tempest recommends their **REST and WebSocket APIs** (personal access token) as the primary source and UDP as the off-grid fallback.
- **Plan:** UDP listener for live data, with the REST API as an optional supplement for history and derived values. The laptop must be on the same subnet or VLAN as the hub.

### 4.6 Starlink

- The dish exposes a local **gRPC** service at `192.168.100.1:9200` (`SpaceX.API.Device.Device/Handle`, with `get_status` and `get_history`).
- **Tools:** `sparky8512/starlink-grpc-tools` (Python, Docker image available; status, history, usage stats, obstruction map; outputs to SQLite, MQTT, Prometheus, and others).
- **Usage caveat:** the history buffer is about **15 minutes**, so the collector must run continuously and integrate throughput into cumulative bytes. Laptop downtime leaves gaps. No local source was found for the *billed* account usage, so label usage as **approximate**.

### 4.7 Remote access and push

- **Recommended: Cloudflare Tunnel** (outbound-only, works behind Starlink's NAT, gives the public HTTPS URL the PWA needs).
  - WebRTC won't traverse the tunnel. Use go2rtc's **MSE/HLS over HTTPS** for remote live view (higher latency).
  - Cloudflare's terms have historically restricted heavy video through their proxy. **[VERIFY]** the current terms before relying on it for video.
- **Alternative: Tailscale.** WebRTC works, but every family member must install Tailscale.
- **Web Push:**
  - Standard VAPID Web Push; the server stores subscriptions per user and per device.
  - On iPhone, Web Push only works after the PWA is **added to the Home Screen** (iOS 16.4+).
  - Push leaves through outbound connections to Apple and Google, so no inbound port is needed.
- **Never expose camera or SDR ports to the internet.** Only the app is reachable through the tunnel.

---

## 5. Proposed architecture (to confirm during planning)

```
                         Internet (family phones/PCs)
                                   │ HTTPS
                          Cloudflare Tunnel (cloudflared)
                                   │
┌────────────────────────── Laptop (Debian + Docker Compose) ──────────────────────────┐
│  app (web UI + API + auth + push + schedulers)  ── SQLite (or Postgres if needed)     │
│     │  ├─ camera module ── reolink HTTP API / reolink_aio ──► TrackMix (LAN)          │
│     │  ├─ LAN-only HTTP receiver  ◄── TrackMix webhook (plain HTTP)                   │
│     │  ├─ radio module ── reads recordings dir; proxies Icecast                       │
│     │  ├─ weather module ── UDP 50222 listener (+ optional Tempest REST)              │
│     │  └─ starlink module ── starlink-grpc-tools output (SQLite)                       │
│  go2rtc ── RTSP from TrackMix ─► MSE/HLS/WebRTC to browser                           │
│  rtl_airband ── RTL-SDR #1 scan+record (files) + Icecast stream                       │
│  (optional) second SDR service for live tuning on RTL-SDR #2                          │
│  icecast                                                                              │
│  starlink collector                                                                   │
│  backup job ── SQLite + config off-site (e.g., OneDrive via rclone)                   │
└───────────────────────────────────────────────────────────────────────────────────────┘
```

**Principles**
- One `docker-compose.yml`; one `.env` for secrets (camera credentials, OAuth client, VAPID keys, Cloudflare token). Never commit secrets.
- Create a **dedicated non-admin camera user** on the TrackMix for the app if the camera's permissions allow PTZ and playback for it.
- Health page showing status for each integration (camera reachable, SDR running, last Tempest packet, last Starlink poll).
- Structured logs; log rotation so the laptop disk doesn't fill.

---

## 6. Data model sketch

- `users` (id, name, email, auth_provider, role, created_at)
- `invites` (token, email, created_by, expires_at, used_at)
- `push_subscriptions` (user_id, endpoint, keys, device_label, created_at)
- `alert_prefs` (user_id, camera_id, detection_types, enabled)
- `alert_mutes` (user_id, camera_id nullable, muted_until)
- `camera_events` (camera_id, type, received_at, payload_json, snapshot_path)
- `reservations` (user_id, start_date, end_date, note, created_at)
- `shopping_items` (text, added_by, added_at, acquired_by, acquired_at)
- `tasks` (title, notes, priority, assignee, created_by, created_at, done_by, done_at)
- `radio_channels` (group, label, freq_mhz, mode, enabled)
- `radio_recordings` (channel_id/freq, started_at, duration_s, file_path)
- `weather_obs` (ts, fields…), `starlink_samples` (ts, fields…)

---

## 7. Build phases

Each phase ends with a working, deployable increment.

1. **Foundation**
   - Repo, Docker Compose, app skeleton, SQLite, auth (Google + password, invite-only, roles), PWA manifest and service worker.
   - Cloudflare Tunnel.
   - Web Push end to end (test notification).
   - Backups.
2. **Household:** reservations calendar (overlap check, optional iCal), shopping list, to-do list.
3. **Weather and Starlink:** Tempest UDP listener and dashboard; Starlink collector, status, and approximate usage.
4. **TrackMix**
   - **Probe first:** login, stream paths for both lenses, `PtzCtrl`, presets, `Get/SetAutoTrack`, `Search`/`Download`, webhook delivery.
   - Then build: go2rtc live view, PTZ controls, recordings browser and download, alerts with per-user prefs, mutes, and cooldown.
5. **Radio**
   - rtl_airband scan-and-record with Icecast; recordings browser and player; channel groups.
   - Then live listening (second dongle) if D4 = yes.
   - P25 only if D5 = yes.
6. **Argus:** only per decision D2.
7. **Later:** move recordings to a local HDD (record RTSP on the laptop) behind the existing recordings interface.

---

## 8. Risks

- **Reolink firmware or API changes:** pin firmware once working; keep probe scripts as regression checks.
- **Laptop failure** takes everything down. Back up the DB and config off-site; document a rebuild.
- **Upload bandwidth:** serve sub-streams remotely by default; load 4K only on demand.
- **Cold:** both cameras are rated to about −10°C / 14°F; northern AZ can go colder.
- **Alert fatigue from wildlife:** cooldowns, detection-type filters, and mutes are required, not optional.

---

## 9. Open decisions (resolve with Chris before coding)

- **D1 — Backend language and stack: Python or C#/.NET?** Python has `reolink_aio` and `starlink-grpc-tools` natively. .NET can call the Reolink JSON API directly and run the Starlink collector as a separate container. Also choose the frontend approach (server-rendered vs SPA) and the auth library to match.
- **D2 — Argus Solar:**
  - (a) Reolink app only
  - (b) Add a Reolink Home Hub so it exposes third-party protocols
  - (c) Try the experimental direct `reolink_aio` support (no live view)
  - (d) Return it for a camera with wired power
- **D3 — Remote access:** Cloudflare Tunnel (recommended for a family PWA) or Tailscale.
- **D4 — Buy a second RTL-SDR** so live tuning doesn't interrupt scan-and-record?
- **D5 — P25 needed?** Confirm cabin location, which agencies matter, and whether they're analog, P25 clear, or encrypted.
- **D6 — Retention targets** for camera video and radio recordings; when to add the HDD.
- **D7 — Domain name** for the app (needed for Cloudflare Tunnel and the Google OAuth redirect URI).
- **D8 — Users and roles:** who's admin; can members control PTZ, or only view?

---

## 10. Sources

- Reolink webhook overview — https://support.reolink.com/articles/46238508855193-Overview-of-Webhook-in-Reolink-Cameras/
- Reolink battery cameras and third-party software — https://support.reolink.com/hc/en-us/articles/360004441753-Why-Reolink-Battery-Powered-Cameras-Cannot-Work-with-3rd-Party-Software/
- Reolink Home Hub compatibility — https://support.reolink.com/articles/32379509281561-Reolink-Home-Hub-Compatibility/
- HA community, battery camera support 2026.6 — https://community.home-assistant.io/t/support-for-reolink-battery-devices-as-of-2026-6/1012766
- reolink_aio — https://pypi.org/project/reolink_aio/ and https://github.com/starkillerOG/reolink_aio
- Reolink PTZ API (OpenAPI) — https://apis.io/apis/reolink/reolink-ptz-api/
- Reolink API examples (gist) — https://gist.github.com/jasonk/4772d1cd5154069cfc9eed07acb2057a
- reolink-download (Login/Search/Download flow) — https://pypi.org/project/reolink-download/
- TrackMix SD download via API works (Reolink community) — https://community.reolink.com/topic/17879/problem-downloading-on-rlc-823s2-via-api
- HA Reolink strings (no HTTPS push) — https://git.sudo.is/home-assistant/core/src/branch/dev/homeassistant/components/reolink/strings.json
- TrackMix streams via ONVIF (SecuritySpy forum) — https://bensoftware.com/forum/discussion/comment/14798/
- TrackMix telephoto resolution — https://www.cnx-software.com/2022/10/15/reolink-trackmix-poe-review-a-smart-4k-ptz-security-camera-with-two-lenses-auto-tracking/ and https://reolink.com/blog/reolink-trackmix-review/
- TrackMix zoom behavior — https://community.reolink.com/post/29205
- RTLSDR-Airband wiki — https://github.com/rtl-airband/RTLSDR-Airband/wiki ; scan mode — https://github.com/charlie-foxtrot/RTLSDR-Airband/wiki/Configuring-channels-for-scan-mode
- Flagstaff public safety feed (channel list) — https://www.broadcastify.com/listen/feed/44418
- CCSO P25 report — https://forums.radioreference.com/threads/coconino-county-sheriff-digital.489556
- Tempest UDP docs — https://apidocs.tempestwx.com/reference/tempest-udp-broadcast
- starlink-grpc-tools — https://github.com/sparky8512/starlink-grpc-tools
