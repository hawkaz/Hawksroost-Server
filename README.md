# Hawksroost — Cabin Hub

A private, invite-only web app (installable PWA) for the Hawk family cabin at
Mormon Lake, AZ. It covers cabin bookings, shopping and to-do lists, Tempest
weather, Starlink status, Reolink cameras, and later a radio scanner. It runs on
one laptop at the cabin and is reached at **https://hawksroost.live** through a
Cloudflare Tunnel.

| Doc | What's in it |
|---|---|
| [docs/PLAN.md](docs/PLAN.md) | Phases, decisions, open questions, **current status** |
| [docs/CABIN_PROJECT_BRIEF.md](docs/CABIN_PROJECT_BRIEF.md) | Requirements and device research |
| [branding/](branding/) | App brand guide and logo files |
| [CLAUDE.md](CLAUDE.md) | Stack and conventions for Claude Code |
| [sdr/](sdr/) | Earlier radio-scanner work (Phase 6, built last) |

## Status

Planning is done. The next step is **Phase 0, host prep**. See [docs/PLAN.md](docs/PLAN.md).

## Updating the server

After a change is pushed, run this over SSH on the cabin laptop:

```bash
cd /opt/hawksroost && git pull && docker compose up -d --build
```
