# Radio — hardware notes and Mormon Lake channels

The software side (channels, scan settings, retention) is set in the app:
**Admin → Radio**. "Load Mormon Lake list" adds everything below.

## RTL-SDR Blog V4

- The V4 needs the RTL-SDR Blog driver fork. The recorder image
  (`ghcr.io/rtl-airband/rtlsdr-airband`) builds it in; nothing needed on the host.
- The kernel's DVB TV driver must be blacklisted or it grabs the dongle.
  `scripts/radio-preflight.sh` checks this.
- **Only one program can own a dongle.** OpenWebRX gets removed when the radio starts
  ([DEPLOY.md](DEPLOY.md), Radio).

## One dongle, ~2 MHz at a time

| Mode | When | Trade-off |
|---|---|---|
| **Multichannel** | All channels fit inside ~1.6 MHz | Hears every channel at once |
| **Scan** | Channels spread wider | Hops between channels; misses simultaneous traffic |

The app picks the mode from the channels that are on. The core Mormon Lake set
spans 154–172 MHz, so one dongle **scans**. With a second dongle, the best split is:

| Window | Span | Covers |
|---|---|---|
| 153.935–155.970 | 2.04 MHz (tight; edge channels near roll-off) | Local fire/EMS + Sheriff |
| 171.425–172.300 | 0.88 MHz | Forest Service North, South, TAC 1 — all at once |
| 166.96–168.78 | 1.8 MHz | Air-to-ground and Forest Service tactical |

Add a dongle: plug it in, set a serial (`rtl_eeprom -s hawk-2` while nothing holds it), add it in Admin → Radio, move channels to it, Apply.

## Antenna

Single roof coax from a Comet GP-6 (2 m / 70 cm). 154–172 MHz is off-band for it;
expect to need more gain or a VHF antenna. More dongles on one coax need a powered multicoupler.

## Mormon Lake channel list (researched 2026-10-31)

Analog only (RTLSDR-Airband decodes AM/NFM). **On** = in the starting scan.
**Alert** = busy-channel notifications. Tone = repeater CTCSS (filters out other users of the frequency).

| Group | Channel | MHz | Tone | On | Alert | Confidence | Src |
|---|---|---|---|---|---|---|---|
| Fire/EMS | Mormon Lake FD dispatch | 155.6175 | 162.2 | ✓ | ✓ | RR database only | A |
| Fire/EMS | Fire mutual aid (VFIRE21) | 154.280 | — | ✓ | ✓ | verified | A, B |
| Fire/EMS | Highlands FD dispatch | 154.175 | 100.0 | ✓ | | verified | A |
| Fire/EMS | Summit FD Ops 1 | 154.385 | — | ✓ | | verified | A |
| Fire/EMS | Pinewood FD dispatch | 154.190 | 192.8 | ✓ | | verified | A |
| Fire/EMS | Ponderosa FD dispatch | 155.295 | — | ✓ | | verified | A |
| Fire/EMS | Summit FD Ops 2 / SW Ops | 154.160 / 155.430 | 91.5 / 127.3 | | | verified | A |
| Fire/EMS | Pinewood FD ops / Ponderosa tac | 154.235 / 154.430 | 94.8 / — | | | verified | A |
| Fire/EMS | Blue Ridge FD (3 repeaters) | 154.205 / 155.970 / 154.145 | 156.7 | | | verified | A |
| Fire/EMS | Flagstaff FD alarm | 153.935 | 100.0 | | | likely; FD mostly P25 now | A |
| Fire/EMS | Guardian Medical tac / rpt | 155.325 / 155.790 | 131.8 | | | old; now listed DMR | A |
| Sheriff | CCSO 2C dispatch, Mormon Mtn | 155.0175 | 114.8 | ✓ | | conflict (see below) | A |
| Sheriff | CCSO 2A dispatch, Flagstaff | 155.835 | 114.8 | ✓ | | conflict | A, C, D |
| Sheriff | CCSO 2A, O'Leary Peak | 155.640 | 114.8 | | | conflict | A |
| Sheriff | AZ DPS District 2 | 460.025 | 100.0 | | | verified (also on P25 statewide) | E, C |
| Forest Service | Coconino NF South net | 172.300 | — | ✓ | ✓ | verified — best wildfire indicator | B, F, C |
| Forest Service | Coconino NF North net | 171.425 | — | ✓ | | verified | B, F, C |
| Forest Service | Flagstaff dispatch TAC 1 | 171.550 | — | ✓ | ✓ | verified | B, A |
| Forest Service | Air-to-ground 1 | 168.725 | — | ✓ | ✓ | verified | G, C |
| Forest Service | Air-to-ground 2 / 3 | 166.9625 / 168.6625 | — | | ✓ | verified | G, C |
| Forest Service | TAC 2 / TAC 3 | 168.675 / 168.775 | — | | | 2016 listing | B |
| Forest Service | Flight following | 168.650 | — | | | verified | B, H |
| Forest Service | AZ Forestry (DFFM) Elden | 151.400 | 123.0 | | | conflict: Broadcastify uses 151.415 | I, H, C |
| Weather | NOAA WXK76 Flagstaff / WWG41 Payson | 162.400 / 162.425 | — | | | verified | J |

Not loaded (air-to-air is AM aircraft band, add by hand if wanted): air-to-air 1 / 2 at 135.975 / 126.625 MHz AM (G); Air Guard 168.625 (emergency only).

### Skipped — digital, trunked or encrypted

| System | Who | Why |
|---|---|---|
| Flagstaff / NAU / ASU P25 | Flagstaff Fire & Police, NAU | P25 Phase II trunked |
| AZ WINS | DPS statewide | P25 Phase II trunked |
| Guardian Medical Transport | Ambulance | DMR |
| Northern Arizona Healthcare | Flagstaff Medical Center | DMR |
| County Roads 453.350 | Roads | P25 |
| CCSO 2A (maybe more districts) | Sheriff | Reported moved to P25 on the same VHF frequencies (~mid-2025), encryption reportedly planned |

### Caveats

- **Sheriff:** the database still lists analog, but a 2025 forum report says 2A went P25 on the same frequencies. Listen to 155.835 and 155.0175: data noise or nothing means P25 — turn them off. The database lists Mormon Mtn as site 2C, while the Broadcastify feed says district 2A covers Mormon Lake.
- **Mormon Lake FD 155.6175** comes from the database only; nothing confirmed who dispatches it today or how busy it is. Listen before trusting its alerts.
- **Forest Service** data is from a 2016 guide but matches today's database and a live feed for 172.300 / 171.425.
- **Alerts** are on channels where a burst of traffic means something (fire dispatch, Forest Service South, TAC 1, air-to-ground). Sheriff and carrier-squelch nets chatter all day, so they don't alert.

### Sources

- A — RadioReference, Coconino County: https://www.radioreference.com/db/browse/ctid/95
- B — 2016 Southwest Area Communication Guide (Flagstaff, pp. 20–21): https://gacc.nifc.gov/swcc/dc/azpdc/operations/documents/aircraft/links/2016%20SW%20Communication%20Guide.pdf
- C — Broadcastify feed 37583 (Munds Park): https://www.broadcastify.com/listen/feed/37583
- D — RadioReference forum, Coconino County Sheriff digital: https://forums.radioreference.com/threads/coconino-county-sheriff-digital.489556/ (search snippets only)
- E — RadioReference, AZ DPS: https://www.radioreference.com/db/aid/126
- F — RadioReference, Coconino NF: https://www.radioreference.com/db/subcat/73716
- G — RadioReference, wildland aviation: https://www.radioreference.com/db/subcat/33789
- H — 2015 National Aviation Frequency Guide: https://gacc.nifc.gov/gbcc/dispatch/ut-cdc/aviation/docs/National%20Aviation%20Frequency%20Guide%20Web.pdf
- I — RadioReference, AZ DFFM: https://www.radioreference.com/db/aid/825
- J — NOAA Weather Radio stations: https://www.weather.gov/source/nwr/JS/CCL.js
