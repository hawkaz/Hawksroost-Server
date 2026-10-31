# Radio — hardware notes

What the radio phase depends on. The software side (channels, scan settings,
retention) is configured in the app: **Settings → Radio**.

## RTL-SDR Blog V4

- The V4 needs the RTL-SDR Blog driver fork. The recorder image
  (`ghcr.io/rtl-airband/rtlsdr-airband`) builds it in, so nothing is needed on
  the host for the recorder itself.
- The kernel's DVB TV driver must be blacklisted or it grabs the dongle.
  `scripts/radio-preflight.sh` checks this.
- **Only one program can own a dongle.** OpenWebRX (`owrx`) currently uses it.
  Stop and remove OpenWebRX before starting the radio recorder.

## One dongle, ~2 MHz at a time

An RTL-SDR digitises about 2.4 MHz, ~2 MHz usable around its centre frequency.

| Mode | When | Trade-off |
|---|---|---|
| **Multichannel** | All channels fit inside ~2 MHz | Hears every channel at once |
| **Scan** | Channels spread wider (e.g. 154–172 MHz) | Hops between channels; misses simultaneous traffic |

The app picks the mode per dongle from its channel list and refuses a
multichannel set that doesn't fit. Adding a dongle later = plug it in, give it a
serial, add it in Settings → Radio. Select dongles by serial once there's more
than one (`rtl_eeprom -s hawk-2`, run while nothing holds the dongle).

## Antenna

Single roof coax from a Comet GP-6 (tuned for 2 m / 70 cm). VHF public-safety
(154–172 MHz) is off-band for it, so expect to need more gain or a VHF antenna.
More dongles on one coax need a powered multicoupler.

## Seed channels — verify before trusting

From a Broadcastify feed description; verify on
[RadioReference, Coconino County](https://www.radioreference.com/db/browse/ctid/95).

| Group | Label | MHz | Notes |
|---|---|---|---|
| Sheriff | CCSO-1 | 155.490 | May have moved to P25 [VERIFY] |
| Sheriff | CCSO-2 Dispatch | 155.835 | [VERIFY] |
| Fire/EMS | Highlands Dispatch | 154.175 | |
| Fire/EMS | Pinewood Dispatch | 154.190 | |
| Fire/EMS | Pinewood Ops | 154.235 | |
| Fire/EMS | Ponderosa Dispatch | 154.430 | |
| Forest Service | Coconino North | 171.425 | Incident channel |
| Forest Service | Coconino South | 172.300 | Incident channel |
| Weather | NOAA WXK76 | 162.400 | Continuous carrier — don't mark as incident |

These load as **disabled** seeds; enable them in Settings → Radio once verified.

## P25

RTLSDR-Airband decodes AM/NFM only. Flagstaff's P25 talkgroups would need a
separate decoder (SDRTrunk / trunk-recorder) on its own dongle. Not planned now.
Encrypted talkgroups are never monitored.
