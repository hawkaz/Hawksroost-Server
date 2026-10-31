# Channel plan (seed) — VERIFY EVERY FREQ

This is the **single source of truth** for the channel list and, crucially, the
per-channel **`incident`** flag. The incident-detection service (Step 4) reads
this mapping (it becomes a YAML config) to decide which channels can trigger an
incident — **independent of which dongle/band block they live in.**

> ⚠️ **All freqs below are SEEDS / placeholders.** Verify each against
> RadioReference — Coconino County, AZ:
> <https://www.radioreference.com/db/browse/ctid/95>
> DB entries change and some seeds come from secondary sources. Do not trust any
> of these on-air until you confirm them.

## Seed channels

| Freq (MHz) | Label | Mod | BW (kHz) | `incident` | Cluster / window | Verify | Notes |
|---|---|---|---|---|---|---|---|
| 162.400 | NOAA WXK76 | nfm | 5 | `false` | NOAA (~162.5) | known | Continuous carrier; **Step 1 smoke test**; EAS alerts |
| 155.490 | Coconino SO | nfm | 12.5 | `false` | Sheriff (~155.66) | **TODO** | Law dispatch; set `true` if you want law calls to trigger incidents |
| 155.835 | Coconino SO 2 | nfm | 12.5 | `false` | Sheriff (~155.66) | **TODO** | Secondary law |
| ~168–173 | USFS / AZ forestry net(s) | nfm | 12.5 | **`true`** | Forestry (pick sub-window) | **TODO** | **Priority incident channels** — fill exact freqs |
| 462.550 | GMRS 550 | nfm | 12.5 | `false` | GMRS (~462.64) | **TODO** | Repeater output |
| 462.575–462.725 | GMRS 575…725 | nfm | 12.5 | `false` | GMRS (~462.64) | **TODO** | Other GMRS repeater outputs |
| 144–148 | Ham 2m repeaters/simplex | nfm | 12.5 | `false` | 2m | **fill in** | Your local repeater outputs |
| 440–450 | Ham 70cm repeaters/simplex | nfm | 12.5 | `false` | 70cm | **fill in** | Your local repeater outputs |

## What `incident: true` means

A channel flagged `incident: true` is one the Step-4 service watches for
**sustained activity** (an incident or fire call). When activity crosses your
configured threshold (e.g. *N transmissions within M minutes*, and/or
*aggregate active-seconds in a window*), the service:

1. **tags** the event so it's visible/filterable in rdio-scanner (and/or an
   incident log),
2. optionally **raises priority**,
3. **extends recording** through a configurable **cooldown** after activity
   stops, and
4. **alerts** you (ntfy / email) with a de-duped incident summary + a link into
   rdio-scanner.

All thresholds, cooldown, and notifier settings will be **config, not
hard-coded**. The `incident` flag here is what selects *which* channels feed
that logic.

## Suggested first incident set

Once verified, mark the **forestry/wildfire dispatch + tac** freqs `incident:
true`. Decide whether **sheriff dispatch** should also count as an incident — if
yes, flip those `false` → `true`. NOAA and ham stay `false` (NOAA is a
continuous carrier and would false-trigger constantly).

## How this maps to `rtl_airband.conf`

- The **recorder** doesn't know about "incidents" — it just records channels.
  Channel identity is carried in each output's `filename_template` /
  `label` (and `include_freq = true` stamps the freq into the filename).
- The **incident service** matches those recordings back to this table by
  freq/label, applies the `incident` flag, and acts. Keep labels/templates here
  and in `rtl_airband.conf` consistent so the join is unambiguous.
