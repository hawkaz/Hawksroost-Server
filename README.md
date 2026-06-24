# Hawksroost Server

Self-hosted, Dockerized platform to remotely monitor analog VHF/UHF radio from
the cabin at **Mormon Lake, AZ (Coconino County)** — with a polished web/mobile
UI, automatic per-transmission recording, and a custom **incident-detection**
layer that flags sustained fire/dispatch activity, keeps recording through a
cooldown, and alerts you.

We **compose proven engines** and write only the orchestration glue on top:

| Layer | Engine | Role |
|---|---|---|
| Recorder | **RTLSDR-Airband** | Parallel multi-channel, squelch-triggered, **one audio file per transmission** |
| UI | **rdio-scanner** | Web + mobile "scanner" UI; ingests airband's files via **dirwatch** |
| Incidents | **custom service** (we write this) | Watches recording activity, applies rules, tags incidents, extends recording, **alerts** |
| Glue | **Docker Compose** | Wires it together with USB passthrough, volumes, restart policies |

> **Deferred (not now):** the local P25 trunked system (Flagstaff PD/fire/city).
> May be out of range / Phase 2 / encrypted. We leave clean extension points to
> add `trunk-recorder` or `SDRTrunk` later as another rdio-scanner source, but
> build **only the analog path** now. We **never** decode/defeat encryption —
> passive monitoring of unencrypted analog signals only.

---

## Where we are: Step 1 of 5

We build and verify **incrementally**, confirming each stage before the next:

- [x] **Step 1 — Recording.** RTLSDR-Airband records the NOAA test channel
  (162.400) to files. ← **you are here; test this, then we continue**
- [ ] Step 2 — UI. rdio-scanner ingests those files via dirwatch.
- [ ] Step 3 — Compose both together.
- [ ] Step 4 — Incident detection: rules + alerts + cooldown recording.
- [ ] Step 5 — Tailscale remote access + multi-user auth + storage retention.

This commit delivers **Step 1 only**: `docker-compose.yml` (recorder service)
and a templated `rtl_airband.conf`. Everything else is scaffolded with clear
"added in Step N" markers so the shape is visible without half-built code.

---

## Repo layout

```
.
├── docker-compose.yml          # Step 1: rtlsdr-airband service (more added later)
├── .env.example                # copy to .env (TZ=America/Phoenix, etc.)
├── Makefile                    # make preflight | up | logs | verify | down
├── scripts/
│   ├── preflight.sh            # host checks: dongle, blacklist, SDR contention
│   └── verify-recording.sh     # "did .mp3 files land?"
├── rtlsdr-airband/
│   └── rtl_airband.conf        # ACTIVE: NOAA 162.400; commented roadmap below it
├── recordings/                 # bind-mount target for audio (gitignored)
├── docs/
│   ├── PREFLIGHT.md            # the v4-driver story + blacklist + owrx contention
│   ├── STEP-1-recording.md     # exact test procedure + troubleshooting
│   ├── band-planning.md        # the ~2 MHz-per-dongle math + cluster plan
│   └── channel-plan.md         # seed freqs + incident flags + RadioReference TODO
├── rdio-scanner/   (Step 2)    # placeholder
└── incident-service/ (Step 4)  # placeholder
```

---

## Step 1 quick start (on the cabin host)

```bash
git pull                                  # get this branch onto HAWKSROOST
./scripts/preflight.sh                     # dongle present? blacklisted? free?
docker stop owrx                           # FREE THE SDR (OpenWebRX holds it now)
cp .env.example .env                        # adjust if you like
docker compose up -d rtlsdr-airband
docker compose logs -f rtlsdr-airband      # watch it tune & open the file
./scripts/verify-recording.sh              # list recent .mp3 files
```

Success = a growing `recordings/NOAA_162.400_*.mp3` you can play. Full detail
and troubleshooting: **[docs/STEP-1-recording.md](docs/STEP-1-recording.md)**.

---

## Three hard realities baked into this design

1. **RTL-SDR v4 needs the Blog driver.** Stock librtlsdr can't tune a v4. Our
   image (`ghcr.io/charlie-foxtrot/rtlsdr-airband`) builds the
   `rtlsdrblog/rtl-sdr-blog` fork, so the v4 works **inside the container**.
   Your host already has the v4 drivers + `dvb_usb_rtl28xxu` blacklisted
   (preflight re-checks). See **[docs/PREFLIGHT.md](docs/PREFLIGHT.md)**.

2. **One dongle = one ~2 MHz window.** At `sample_rate = 2.40`, a dongle sees
   ~`centerfreq ± 1.0 MHz`. Your targets span 155–467 MHz, so **one dongle can
   only camp one cluster at a time**. Architecture is **one dongle per band
   cluster** (extra dongles = extra commented `devices:` blocks, selected by
   serial). See **[docs/band-planning.md](docs/band-planning.md)**.

3. **The dongle serves one program at a time.** While this recorder owns the
   dongle, **OpenWebRX cannot** use the same one (and vice-versa). Running both
   live needs a **second dongle** (ideally fed by a multicoupler off the one
   coax). For now, `docker stop owrx` before recording.

---

## Pinning & Watchtower

Your host runs **Watchtower**, which auto-updates `:latest` images. To keep the
SDR stack reproducible, each service here carries
`com.centurylinklabs.watchtower.enable=false`. Once a version proves good,
**pin it** — e.g. replace `:latest` with a specific release tag in
`docker-compose.yml` — and you control upgrades deliberately.

---

## How to… (grows as we build)

- **Add a channel** in the same band as an active dongle: add a `{ freq=…; … }`
  block to that device's `channels:` list in `rtl_airband.conf`. Verify the freq
  on [RadioReference](https://www.radioreference.com/db/browse/ctid/95) first.
- **Add a dongle for a new band:** uncomment the matching `DEVICE n` block in
  `rtl_airband.conf`, set its `serial`, pick `centerfreq` for that ~2 MHz window.
- **Tune squelch / incident thresholds, remote access, retention, the deferred
  P25 source:** documented as we reach Steps 2–5.
