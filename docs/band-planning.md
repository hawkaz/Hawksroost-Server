# Band planning — why "one dongle per cluster"

## The ~2 MHz window

An RTL-SDR samples a slice of spectrum, not a single channel. At
`sample_rate = 2.40` Msps it digitizes ~2.4 MHz, of which ~**2.0 MHz is usable**
(edges roll off / alias). RTLSDR-Airband then demodulates **all** your listed
channels **inside that window, in parallel** — it does not hop or scan-and-camp.

```
usable window  ≈  centerfreq − 1.0 MHz  ..  centerfreq + 1.0 MHz
```

Keep channels slightly off `centerfreq` — a DC spike sits exactly at center.

## Your targets don't fit in one window

| Cluster | Freqs (MHz) | Span | Fits one ~2 MHz window? |
|---|---|---|---|
| Sheriff / law | 155.490, 155.835 | 0.35 MHz | ✅ yes (center ~155.66) |
| NOAA weather | 162.400–162.550 | 0.15 MHz | ✅ yes (center ~162.5) |
| **Forestry / fire** | ~168–173 | **~5 MHz** | ❌ no — pick a sub-window |
| GMRS (outputs) | 462.550–462.725 | 0.18 MHz | ✅ yes (center ~462.64) |
| GMRS (inputs) | 467.x | +5 MHz from outputs | ❌ separate window |
| Ham 2m | 144–148 | 4 MHz | pick specific repeater freqs |
| Ham 70cm | 440–450 | 10 MHz | pick specific repeater freqs |

Sheriff (155), NOAA/forestry (162–173) and GMRS (462) are **>5 MHz apart** —
**no single dongle can watch across those gaps.** Hence the architecture:

> **One physical dongle = one `devices:` block = one ~2 MHz window.**

## The plan, by dongle count

- **1 dongle (today):** camp ONE cluster.
  - *Step 1:* NOAA window (smoke test).
  - *Then:* re-park onto a **forestry/fire sub-window** — your priority incident
    channels — once verified on RadioReference. (168–173 is itself wider than one
    window, so choose the ~2 MHz that holds the busiest dispatch/tac freqs.)
- **2 dongles:** forestry/fire **+** sheriff (or NOAA).
- **3–4 dongles:** add GMRS/70cm, and split forestry into two sub-windows.

Each added dongle is a commented `DEVICE n` block in `rtl_airband.conf` — set
its `serial` and `centerfreq` and uncomment.

## One coax, several dongles

You have a single roof run from the **Comet GP-6** (tuned for 2m/70cm; off-band
VHF like 155/162/168–173 is received with reduced efficiency — expect to add
gain, and a dedicated VHF antenna later). To feed multiple dongles from one
coax, use a **powered multicoupler** (active splitter) so each dongle gets a
full-strength copy. Give each dongle a unique **serial** (`rtl_eeprom -s name`)
so USB replugs never swap their identities.

## Selecting dongles by serial

Indexes change when you move USB ports; serials don't. With one dongle, `index =
0` is fine. With more, switch every block to `serial = "…"`:

```bash
rtl_test                       # lists serial(s)
rtl_eeprom -s hawk-fire        # set a memorable serial (nothing else holding it)
```

## Extension point: the deferred P25 trunked system

Flagstaff's P25 trunk (PD/fire/city) is **out of scope now** (range / Phase 2 /
possibly encrypted — we never touch encryption). When you add it later, it does
**not** go through RTLSDR-Airband. Instead run **`trunk-recorder`** (or
**SDRTrunk**) on its own dongle(s), and point it at the **same rdio-scanner** as
a separate *system* (via dirwatch or rdio-scanner's call-upload API). The analog
path we're building and the trunked path stay independent, sharing only the UI.
That's the clean seam we're preserving — nothing here blocks it.
