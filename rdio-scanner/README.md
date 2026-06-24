# rdio-scanner — Step 2 (placeholder)

The web + mobile UI that other (non-technical) users will use. It **ingests
RTLSDR-Airband's per-transmission files via `dirwatch`** (a known-working combo)
and presents them like a police scanner.

**Added in Step 2** (after you confirm Step 1 recording works):

- `rdio-scanner` service in `docker-compose.yml` (named volume for its SQLite
  DB; image `ghcr.io/chuot/rdio-scanner`).
- A **dirwatch** config pointed at `/recordings`, with a filename **mask** that
  parses RTLSDR-Airband's `template_DATE_TIME_FREQ.mp3` (using the `#TGHZ` /
  `#TGKHZ` / `#TGMHZ` meta tags) into the right *system* / *talkgroup*.
- A **systems/talkgroups** mapping for the analog channels (each freq → a
  talkgroup; clusters → systems), aligned with
  [../docs/channel-plan.md](../docs/channel-plan.md).
- **Multi-user access** (downstream/auth) so the other users get logins.

For Step 1 we deliberately keep the surface small: get audio on disk first.
