# Hawksroost — Cabin Hub

A private, invite-only web app for the Hawk family cabin at Mormon Lake, AZ, made
for phones, tablets and computers alike (and installable on each): cabin visits,
shopping and other lists, Tempest weather, Starlink, IP cameras (Reolink, ONVIF or
any video address) with motion alerts, and a radio scanner. It runs on one laptop
at the cabin and is reached at **https://hawksroost.live** (Starlink public IP,
HTTPS by Caddy).

| Doc | What's in it |
|---|---|
| [docs/PLAN.md](docs/PLAN.md) | **Status**, decisions, things to review |
| [docs/DEPLOY.md](docs/DEPLOY.md) | Install, update, roll back, back up — step by step |
| [docs/RADIO.md](docs/RADIO.md) | How calls are saved, live listening, tuning; hardware and channels |
| [docs/CABIN_PROJECT_BRIEF.md](docs/CABIN_PROJECT_BRIEF.md) | Original requirements and device research |
| [branding/](branding/) | App brand guide and logo files |
| [CLAUDE.md](CLAUDE.md) | Stack and conventions for Claude Code |

## Update the server

```bash
bash /opt/hawksroost/scripts/update.sh
```
