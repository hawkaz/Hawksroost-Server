# Hawksroost — recording, UI & retention feature spec

**Status:** agreed plan (Jun 2026). Source of truth for the recording / listening /
retention / incident features. Build order maps to the Steps in the top-level
[README](../README.md).

This is the "what and where," decided with eyes open about what each engine can
and can't do. We **compose** RTLSDR-Airband + rdio-scanner and add a custom
control service *around* them — we do **not** fork them.

## The two web surfaces

| Surface | Who uses it | Purpose |
|---|---|---|
| **rdio-scanner** | everyone (you + the non-technical users) | Listen/replay calls (web + mobile); per-call **Download** = export/keep a clip to your own device |
| **Hawk control** (custom service) | you / admins | "DVR settings": curated frequency management, size-cap & retention, the **Keep / review** page, incident rules & alerts |

rdio-scanner stays the polished listening UI (confirmed decision). The custom
service supplies the controls rdio-scanner lacks, without modifying it.

## Engines & where logic lives

- **RTLSDR-Airband** — recorder. Tunes dongle(s), demodulates, squelch, writes
  **one MP3 per transmission** to `/recordings`.
- **rdio-scanner** — listening UI + call store. `dirwatch` ingests airband's
  files (**Delete-After** removes the raw copy → no double storage). Native
  age-prune (`pruneDays`) exists but only as a coarse backstop.
- **Hawk control service** (custom, Python; the `incident-service/` dir) —
  incident detection + alerts + cooldown, **size-based rotation**,
  **protect/Keep**, and the **frequency admin**. Ships a small web admin UI.

## Requirement specs

### R1 — Set monitored frequencies in a UI → *custom; build last*
- **Model: curated channel list.** Toggle known channels on/off; add a channel
  by frequency **within a dongle's ~2 MHz band**, validated so you can't pick
  something the hardware can't hear (see [band-planning.md](band-planning.md)).
- **Mechanism:** admin page edits the channel list → regenerates
  `rtl_airband.conf` → restarts the recorder container. Per-dongle.
- **Why custom:** RTLSDR-Airband is config-file + restart; rdio-scanner's UI
  doesn't control the SDR.
- **Sequence:** built **after** recording/listening/incidents/retention — it's
  the biggest custom chunk and isn't safety-critical.

### R2 — Stop after X silence, restart on activity → *native (RTLSDR-Airband)*
- **Mechanism:** per-channel **squelch** + **`split_on_transmission`** → one MP3
  per transmission. Signal opens the file; silence closes it; next activity =
  new file.
- **Tuning:** silence tail default **~7–10 s** so a back-and-forth isn't shredded
  into many tiny files. Squelch via `squelch_snr_threshold` (dB SNR), per channel.
- **Not the same as incidents:** the *minutes-scale* "keep recording the channel
  after an incident quiets down" is the **cooldown** (R5), a higher-level
  behavior — distinct from the per-transmission split.

### R3 — Listen on the web UI → *native (rdio-scanner)*
- Multi-user, web + mobile. Per-call Play / Replay / Skip / Avoid + **Download**.
- **Download = export/keep** a clip to your device (the NVR "export clip"
  action) — available to every listener, no extra build.
- Multi-user logins/access set in rdio-scanner's admin (Steps 2/5).

### R4 — Rotating recordings + size cap + Keep → *NVR model; mixed*
Mental model = **video surveillance / NVR**: continuous rolling capture, oldest
auto-overwritten to stay under a size budget, important clips protected.
- **Size-capped rolling buffer (custom):** the control service trims the
  **oldest** calls from the store once total audio exceeds the **size cap**.
  rdio-scanner's age-prune is the coarse backstop underneath it.
- **Size limit in the UI (custom):** set the cap (GB, or "keep N% free") on the
  admin page.
- **No double storage (native):** dirwatch **Delete-After** removes the raw
  airband file once ingested.
- **Protect / Keep (custom):** a server-side **protected** flag exempts a clip
  from rotation.
  - **Incidents auto-protect** — a fire/incident clip never rotates away.
  - **Manual Keep = companion "Keep" page (chosen: option 2).** The admin page
    lists recent clips with **Play + Keep**; Keep sets the protected flag so the
    clip stays in the system, shared and un-rotated.
  - Plus rdio-scanner's native **Download** for quick client-side export.
  - *Deferred (option 3):* a Keep button literally inside rdio-scanner's player
    (would require forking rdio-scanner or injecting a script via
    nginx-proxy-manager). Revisit later if wanted.
- **Defaults (all config):** size cap **e.g. 50 GB** (tiny next to your 193 GB
  free; settle once we see real daily volume) · age backstop **14 days** ·
  kept/protected = **forever** · hard safety prune under **~15 % free disk** ·
  silence tail **~7–10 s**.

### R5 — Incident detection + alerts + cooldown → *custom (already in scope)*
- Per-channel **`incident: true`** flag ([channel-plan.md](channel-plan.md))
  selects which channels can trigger — independent of band/dongle.
- Trigger on a configurable rule: *N transmissions in M minutes*, and/or
  *aggregate active-seconds in a window* > X. Parameters are config.
- On trigger: **tag** for rdio-scanner / incident log, **auto-protect** the
  clips (R4), keep recording the channel through a **cooldown** after activity
  ceases, and **alert** (ntfy and/or email) with a **de-duped** summary + a link
  into rdio-scanner.

## Build order (maps to README steps)

1. **Step 1** — recording (NOAA) ✅ mechanical; audio tuning in progress
2. **Step 2** — rdio-scanner listening (R3) + dirwatch + Delete-After
3. **Step 3** — compose both together
4. **Step 4** — control service: incidents + alerts + cooldown (R5); size-rotation
   + protect + **Keep page** (R4)
5. **Step 5** — Tailscale remote access, multi-user auth, retention defaults live
6. **Later** — R1 frequency-admin UI; option-3 in-player Keep; deferred P25 source

## Open items
- Set the real size-cap number once we know typical daily volume.
- Confirm RTLSDR-Airband's exact silence-tail knob during R2 build.
- R1 admin UI and option-3 in-player Keep deferred by choice.
