# Deploy and run on the cabin laptop

Everything runs from `/opt/hawksroost` on the Dell Latitude (Debian, Docker),
over SSH. Integrations (cameras, Tempest, Starlink, email, Google sign-in, radio
channels, sign-in photo) are set up in the app afterwards, under **Admin** —
not on the server.

## Overview

1. **Survey the laptop** (read-only `server-check.sh`) and send Claude the output.
2. **Prepare the server** from that survey — Claude gives the exact steps: OS
   updates, automatic security updates, never sleep (lid closed is fine), clean
   shutdown on low battery, BIOS power-on when AC returns + battery charge
   limit, Docker ready, unneeded containers removed.
3. Deploy key, then put the code in `/opt/hawksroost`.
4. Front door: router port forward, Cloudflare DNS token; run the installer.
5. First admin account.
6. Integrations in the app (camera, Tempest, Starlink, email, Google).
7. Power-loss test: pull the plug, let it come back, check everything restarts.
8. Last: the radio.

## 0. Survey (before anything else)

The code isn't on the laptop yet, so the first time the survey script is pasted
in (Claude provides the block). Afterwards it lives at:

```bash
bash /opt/hawksroost/scripts/server-check.sh | tee ~/server-check.txt
```

## 1. Deploy key (read-only access to the private repo)

Makes an SSH key just for this repo (no passphrase, so updates run unattended):

```bash
ssh-keygen -t ed25519 -N "" -C "hawksroost-laptop" -f ~/.ssh/hawksroost_deploy
```

Tells git to use that key for this repo only (doesn't change any other GitHub access on the laptop):

```bash
printf '\nHost github-hawksroost\n  HostName github.com\n  User git\n  IdentityFile ~/.ssh/hawksroost_deploy\n  IdentitiesOnly yes\n' >> ~/.ssh/config && chmod 600 ~/.ssh/config
```

Shows the public key to copy:

```bash
cat ~/.ssh/hawksroost_deploy.pub
```

In GitHub: **hawkaz/Hawksroost-Server → Settings → Deploy keys → Add deploy key**.
Title `Cabin laptop`, paste the key, leave **Allow write access** off, **Add key**.

## 2. Put the code in place

Creates the folder (needs sudo once):

```bash
sudo mkdir -p /opt/hawksroost && sudo chown "$USER": /opt/hawksroost
```

Clones the `main` branch using the deploy key:

```bash
GIT_SSH_COMMAND="ssh -o StrictHostKeyChecking=accept-new" git clone -b main git@github-hawksroost:hawkaz/Hawksroost-Server.git /opt/hawksroost
```

Success ends with `Resolving deltas: 100%`. `Permission denied (publickey)` means the deploy key isn't added yet.

## Server prep (after the code is in place)

Run once (safe to re-run). Takes a few minutes:

```bash
sudo bash /opt/hawksroost/scripts/server-prep.sh
```

It sets the time zone to America/Phoenix, installs updates, reboots at 4 am
when an update needs it, shuts down cleanly at 7% battery (UPower), allows the
Tempest hub's UDP 50222 broadcasts through ufw, sets Docker log limits, removes
OpenWebRX / nginx-proxy-manager / Portainer / the old test recorder and its
20 GB of recordings, turns Wi-Fi off (Ethernet only) and turns off printing,
Bluetooth and ModemManager, and retires the old `~/Docker` stack (Home Assistant,
Watchtower). Only `~/Docker/rtl-sdr` (driver source) is kept.

Then, at the laptop: **BIOS (F2) → Power Management → AC Behavior → Wake on AC: on**
[VERIFY menu path on the 5420]. Battery charge is already limited to 75–80%.

Power-loss test: unplug the laptop and the router, wait, plug both back in.
Everything should come back by itself within a few minutes.

## 3. Front door (Starlink public IP → laptop)

Starlink Local Priority with the public IP option, Starlink router in bypass
mode, your own router at 192.168.67.1. Caddy on the laptop serves HTTPS with
automatic Let's Encrypt certificates; a small updater keeps the DNS records
pointed at the public IP (Starlink reserves it, but it can change after a
relocation or software update).

1. **Router — fixed address:** reserve `192.168.67.101` for the laptop's Ethernet (DHCP reservation).
2. **Router — port forwarding:** TCP **80** and TCP **443** → `192.168.67.101` (same ports).
3. **Cloudflare — API token:** My Profile → **API Tokens → Create Token → "Edit zone DNS"** template →
   Zone Resources: *Include → Specific zone → hawksroost.live* → Create. Copy the token (the installer asks for it).
4. **Cloudflare — DNS:** nothing to add by hand. The updater creates `hawksroost.live` as
   **DNS only** (grey cloud). Delete any old record for that name that points somewhere else
   (e.g. an old tunnel CNAME).

## 4. Install

Asks for the Cloudflare API token (paste, Enter — it won't show), opens ports
80/443 in the firewall (asks for your sudo password), builds, and starts everything:

```bash
cd /opt/hawksroost && bash scripts/install.sh
```

Success ends with `OK: app is up` and a list of running services. Then
`https://hawksroost.live` shows the sign-in page. On the cabin network it's
also at `http://<laptop-ip>:8080`.

## 5. First admin

Prints a one-time link (good for 2 days):

```bash
bash /opt/hawksroost/scripts/admin-invite.sh
```

Open it, create your account. Everyone else: **Admin → People → Invite**.

## 6. Integrations (in the app)

Each has its own page under **Admin**:

- **Site:** web address `https://hawksroost.live`. Sign-in photo: upload one whenever you like.
- **Cameras → Add camera:** pick the type (Reolink for the cabin camera), its address on the cabin network and a camera login made for the app in the camera's own app → **Test** → **Save**. The test lists what the camera can do (pan/tilt, presets, recordings, siren, light…). Then check it in more detail:

  ```bash
  cd /opt/hawksroost && docker compose exec api python -m probes.reolink
  ```

  Paste the output back to Claude. If live video won't play, run `bash /opt/hawksroost/scripts/camera-check.sh` (read-only; passwords are masked) and send Claude the output.

  **Faster live view (optional):** a live picture can only start at a keyframe, so the time between keyframes on the camera's small (Fluent) stream is the wait when you open a camera. Reolink's phone app doesn't have this setting. On a computer at the cabin, open the camera's address in a browser (or the desktop Reolink Client: Camera Settings → Device → Stream → Settings) → **Device → Stream → Fluent → I-frame Interval → 1x** → Save. 1x is one keyframe a second; it uses a little more of the cabin's upload only while someone watches. [VERIFY the menu names on this camera]
- **Weather:** nothing to enter for live data. Enter the station's elevation in feet (about 7,100 at Mormon Lake [VERIFY the station's own]) to show sea-level pressure. Optional token + station ID for the forecast.
- **Starlink:** the default `192.168.100.1:9200` normally works. Dish restart, stow and the night sleep schedule are on the same page. Check:

  ```bash
  cd /opt/hawksroost && docker compose exec collector python -m probes.starlink
  ```

- **Sign-in & email → Email (Brevo)** — just an API key and a send-from address (`cabin@hawksroost.live`):
  1. Brevo → **Senders, Domains & Dedicated IPs → Domains → Add a domain** → `hawksroost.live`.
  2. Brevo lists DNS records (a Brevo code TXT, DKIM, DMARC). Add each in Cloudflare → hawksroost.live → **DNS** (DNS only, not proxied) → back in Brevo, **Verify**. Brevo may offer to do this automatically for Cloudflare.
  3. Brevo → **SMTP & API → API keys → Generate** (labels vary a little by version [VERIFY]). Name it `hawksroost`, leave MCP off, pick no expiry or the longest offered, copy the key (starts with `xkeysib-`; shown once).
  4. In the app's Email card: paste the key, send-from `cabin@hawksroost.live` → **Save** → **Send test**. If **Send test** says Brevo blocked the cabin's internet address, allow it in Brevo → **Settings → Security → Authorised IPs** (Brevo also emails a link that does it). Starlink's public address can change; when it does, email stops until the new one is allowed, and **Admin → System** shows "Last send failed". Brevo also has a "Deactivate blocking" switch there; it's simpler but leaves the key usable from anywhere if it ever leaks.

  Replies to that address go nowhere unless you forward it (Cloudflare → Email → Email Routing, free) [VERIFY current menu].
- **Sign-in & email → Google sign-in:** follow the steps on that card; it shows the redirect URI to paste into Google Cloud.

**Admin → System** shows what's working. Requests to join from the sign-in page show up in **Admin → People**.

## Updating

After Claude pushes changes:

```bash
bash /opt/hawksroost/scripts/update.sh
```

## Rolling back

Shows recent versions:

```bash
cd /opt/hawksroost && git log --oneline -10
```

Send that list to Claude for the exact command to return to a version.
Database changes only go forward, so check with Claude before rolling back across one.

## Backups

The app copies its database to `/opt/hawksroost/data/backups` every night
(Admin → System → Backups; 14 days kept). There's no off-site copy: if
the laptop dies, the app is rebuilt from GitHub and the bookings and lists start
fresh unless a backup file was copied off first.

Restoring a backup — stop the app:

```bash
cd /opt/hawksroost && docker compose stop api collector
```

List backups:

```bash
cd /opt/hawksroost && ls -1t data/backups | head
```

Claude gives you the copy command for the file you pick, then start again:

```bash
cd /opt/hawksroost && docker compose start api collector
```

## Radio (last)

1. In the app, **Admin → Radio**: tick **Radio scanner on** → **Save**, **Load Mormon Lake list** (adds "Dongle 1" and the channels; 12 core ones start on), then **Apply to recorder**.
2. Start the recorder. It checks the dongle first (USB, TV-tuner driver, nothing else holding it), turns on the `radio` profile and starts the recorder and live-listening server. No sudo:

   ```bash
   bash /opt/hawksroost/scripts/radio-on.sh
   ```

   OpenWebRX, which used to hold the dongle, was already removed by `server-prep.sh`.

How calls are saved, live listening and tuning to one frequency: [RADIO.md](RADIO.md#in-the-app). Hardware notes are there too.

If live listening or recording misbehaves, this read-only check says what's running and what the recorder reports (send Claude the output):

```bash
bash /opt/hawksroost/scripts/radio-check.sh
```

## Useful

| What | Command |
|---|---|
| Status | `cd /opt/hawksroost && docker compose ps` |
| App logs | `cd /opt/hawksroost && docker compose logs --tail=50 api` |
| Weather/Starlink logs | `cd /opt/hawksroost && docker compose logs --tail=50 collector` |
| HTTPS / certificate logs | `cd /opt/hawksroost && docker compose logs --tail=30 caddy` |
| DNS updater logs | `cd /opt/hawksroost && docker compose logs --tail=20 ddns` |
| Restart everything | `cd /opt/hawksroost && docker compose restart` |
| Admin invite link | `bash /opt/hawksroost/scripts/admin-invite.sh` |
| Password reset link | `cd /opt/hawksroost && docker compose exec api python -m app.cli reset-link someone@example.com` |
