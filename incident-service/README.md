# Incident-detection service — Step 4 (placeholder)

The custom orchestration layer (the part that doesn't exist off the shelf). It
watches recording activity/metadata and applies **configurable rules** to flag
fire/dispatch incidents, extend recording, and alert you.

**Added in Step 4** (after recording + UI + compose are proven). Planned shape:

- **Language:** Python, single well-commented **`config.yaml`** exposing all
  thresholds/cooldown/notifier settings (nothing hard-coded).
- **Input:** consumes RTLSDR-Airband's per-transmission output — files +
  metadata (channel/freq, timestamp, duration) under `/recordings`.
- **Activity model:** rolling per-channel state.
- **Trigger:** for any channel flagged `incident: true` (see
  [../docs/channel-plan.md](../docs/channel-plan.md)), fire when activity
  exceeds the rule — e.g. *N transmissions within M minutes* and/or *aggregate
  active-seconds in a window > X*. All parameters are config.
- **On trigger:** tag the event for rdio-scanner (and/or an incident log),
  optionally raise priority, and **keep recording the channel through a
  configurable cooldown** after activity ceases.
- **Alerts:** pluggable notifiers — **ntfy** and/or **email (SMTP)** to start,
  easy to add more. Includes an incident summary (channel, start time, activity
  level) and a link into rdio-scanner. **De-dupe / debounce** so one incident
  doesn't spam.
- **Extension seam:** rules key off the channel `incident` flag, so when the
  deferred P25 trunked source is added later it can feed the same logic.

For Step 1 this is intentionally just a placeholder.
