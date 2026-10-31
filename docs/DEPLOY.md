# Deploy and run on the cabin laptop

Everything runs from `/opt/hawksroost` on the Dell Latitude (Debian, Docker),
over SSH. Integrations (cameras, Tempest, Starlink, email, Google sign-in, radio
channels, sign-in photo) are set up in the app afterwards, under
**Admin → Integrations** and **Admin → Radio** — not on the server.

## Overview

1. **Survey the laptop** (read-only `server-check.sh`) and send Claude the output.
2. **Prepare the server** from that survey — Claude gives the exact steps: OS
   updates, automatic security updates, never sleep (lid closed is fine), clean
   shutdown on low battery, BIOS power-on when AC returns + battery charge
   limit, Docker ready, unneeded containers removed.
3. Deploy key, then put the code in `/opt/hawksroost`.
4. Front door: router port forward, Cloudflare DNS token, Home Assistant proxy setting; run the installer.
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

Run once (safe to re-run). Takes a few minutes; Home Assistant restarts twice:

```bash
sudo bash /opt/hawksroost/scripts/server-prep.sh
```

It sets the time zone to America/Phoenix, installs updates, reboots at 4 am
when an update needs it, shuts down cleanly at 7% battery (UPower), allows the
Tempest hub's UDP 50222 broadcasts through ufw, sets Docker log limits, removes
OpenWebRX / nginx-proxy-manager / Portainer / the old test recorder and its
20 GB of recordings, turns Wi-Fi off (Ethernet only) and turns off printing,
Bluetooth and ModemManager. Home Assistant and Watchtower stay.

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
4. **Cloudflare — DNS:** nothing to add by hand. The updater creates `hawksroost.live` and
   `ha.hawksroost.live` as **DNS only** (grey cloud). Delete any old record for those two names
   that points somewhere else (e.g. an old tunnel CNAME).
5. **Home Assistant:** it must trust Caddy, or it answers "400: Bad Request". Claude gives the exact
   lines for `~/Docker/homeassistant/config/configuration.yaml` after seeing the current file.

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

All under **Admin → Integrations**:

- **General:** public address `https://hawksroost.live`. **Sign-in photo:** upload one whenever you like.
- **Cameras → Add:** the TrackMix's LAN address and a camera user for the app (make one in the Reolink app) → **Test** → **Save**. Then check what the camera supports:

  ```bash
  cd /opt/hawksroost && docker compose exec api python -m probes.reolink
  ```

  Paste the output back to Claude. If live video won't play, set the camera's encoding to H.264 in the Reolink app.
- **Tempest:** nothing to enter for live data. Optional token + station ID for the forecast.
- **Starlink:** the default `192.168.100.1:9200` normally works. Check:

  ```bash
  cd /opt/hawksroost && docker compose exec collector python -m probes.starlink
  ```

- **Email (Brevo)** — sending from `cabin@hawksroost.live`:
  1. Brevo → **Senders, Domains & Dedicated IPs → Domains → Add a domain** → `hawksroost.live`.
  2. Brevo lists DNS records (a Brevo code TXT, DKIM, DMARC). Add each in Cloudflare → hawksroost.live → **DNS** (DNS only, not proxied) → back in Brevo, **Verify**. Brevo may offer to do this automatically for Cloudflare.
  3. In the app's Email card: SMTP login and SMTP key from Brevo → **SMTP & API → SMTP**; from address `cabin@hawksroost.live` → **Send test**.

  Replies to that address go nowhere unless you forward it (Cloudflare → Email → Email Routing, free) [VERIFY current menu].
- **Google sign-in:** follow the steps on that card; it shows the redirect URI to paste into Google Cloud.

**Admin → Health** shows what's working.

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
(Admin → Integrations → Backups; 14 days kept). There's no off-site copy: if
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

1. In the app, **Admin → Radio**: turn the scanner on, **Load Mormon Lake list** (12 core channels start on), **Apply**.
2. Remove OpenWebRX so the recorder can use the dongle (deletes the container, not your other files):

   ```bash
   docker stop owrx && docker rm owrx
   ```

3. Start the recorder (runs the radio preflight first):

   ```bash
   cd /opt/hawksroost && bash scripts/radio-on.sh
   ```

Hardware notes: [RADIO.md](RADIO.md).

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
