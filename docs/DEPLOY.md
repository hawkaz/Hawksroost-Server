# Deploy and run on the cabin laptop

Everything runs from `/opt/hawksroost` on the Dell Latitude (Debian, Docker).
Commands are run over SSH. Integrations (cameras, Tempest, Starlink, email,
Google sign-in, radio channels) are set up in the app afterwards, under
**Admin → Integrations** and **Admin → Radio** — not on the server.

## Overview

1. Check the laptop (read-only script).
2. Battery charge limit in the Dell BIOS.
3. Put the code in `/opt/hawksroost`.
4. Create the Cloudflare tunnel; copy its token.
5. Run the installer (asks for the token, builds, starts).
6. Make the first admin account.
7. In the app: add the camera, check Tempest and Starlink, set up email and Google.
8. Later: off-site backups, then the radio.

---

## 1. Check the laptop

Downloads and runs the read-only inventory script (changes nothing):

```bash
curl -fsSL https://raw.githubusercontent.com/hawkaz/Hawksroost-Server/main/scripts/inventory.sh | bash
```

If the repo is private that URL won't work; run it after step 3 instead:

```bash
bash /opt/hawksroost/scripts/inventory.sh
```

It lists OS, disk, Docker, running containers, ports, whether the Starlink dish
and Tempest hub are reachable, and the RTL-SDR.

## 2. Battery charge limit

An always-plugged-in laptop battery swells if it sits at 100%. In the Dell BIOS
(F2 at boot): **Power → Primary Battery Charge Configuration → Primarily AC use**
(or Custom, 50–80%). Menu names vary by model.

## 3. Put the code in place

Creates the folder (needs sudo once), then clones:

```bash
sudo mkdir -p /opt/hawksroost && sudo chown "$USER": /opt/hawksroost
```

```bash
git clone -b main https://github.com/hawkaz/Hawksroost-Server.git /opt/hawksroost
```

If GitHub asks for a password, use a GitHub personal access token (classic, `repo` scope).

## 4. Cloudflare tunnel

In the Cloudflare dashboard (hawksroost.live must be on Cloudflare DNS):

1. **Zero Trust → Networks → Tunnels** (some accounts show **Networks → Connectors**) → **Create a tunnel** → **Cloudflared**.
2. Name it `hawksroost`. On the install screen pick **Docker**; the command shown ends in a long token after `--token`. Copy just the token.
3. Add a **public hostname / published application route**: subdomain blank, domain `hawksroost.live`, service type **HTTP**, URL `web:80`.

Menu names change often; the pieces that matter are the token and the route to `http://web:80`.

## 5. Install

Asks for the token (paste, Enter), builds, and starts everything:

```bash
cd /opt/hawksroost && bash scripts/install.sh
```

Success ends with `OK: app is up` and a list of running services.
Then `https://hawksroost.live` should show the sign-in page. On the cabin network
it's also at `http://<laptop-ip>:8080`.

## 6. First admin

Prints a one-time link (good for 2 days):

```bash
bash /opt/hawksroost/scripts/admin-invite.sh
```

Open the link, create your account. Then in the app: **Admin → People → Invite** for everyone else.

## 7. Set up integrations (in the app)

All under **Admin → Integrations**:

- **General:** public address `https://hawksroost.live`.
- **Cameras → Add:** the TrackMix's LAN address, a camera user and password → **Test** → **Save**.
  Then check what the camera supports (stream paths, lenses, PTZ, recordings):

  ```bash
  cd /opt/hawksroost && docker compose exec api python -m probes.reolink
  ```

  Paste the output back to Claude. Set the camera's encoding to H.264 in the Reolink app if live video doesn't play.
- **Tempest:** nothing to enter for live data. Optional token + station ID for the forecast.
- **Starlink:** the default address `192.168.100.1:9200` normally works. Check with:

  ```bash
  cd /opt/hawksroost && docker compose exec collector python -m probes.starlink
  ```

- **Email (Brevo):** turn on; login and SMTP key from Brevo → SMTP & API → SMTP; a verified sender address → **Send test**.
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

Send that list to Claude; you'll get the exact command for the version to return to.
Database changes only go forward, so check with Claude before rolling back across one.

## Off-site backups (OneDrive)

The app backs up its database nightly to `/opt/hawksroost/data/backups`. To also
copy those to OneDrive, run:

```bash
cd /opt/hawksroost && bash scripts/setup-offsite.sh
```

rclone asks questions (wording varies by rclone version). Answers: `n` (new remote) → name `onedrive` → storage `onedrive` →
leave client id/secret blank → region `1` (global) → advanced `n` → auto config `n`.
It then asks you to run `rclone authorize "onedrive"` on a computer with a browser —
on your Windows PC, download rclone, run that command, sign in, and paste the token back.
Pick **OneDrive Personal or Business** as fits; accept the defaults after that.

## Restoring from a backup

Stop the app, swap the database, start:

```bash
cd /opt/hawksroost && docker compose stop api collector
```

```bash
cd /opt/hawksroost && ls -1t data/backups | head
```

Then Claude gives you the copy command for the file you pick, followed by:

```bash
cd /opt/hawksroost && docker compose start api collector
```

## Radio (last phase)

1. In the app, **Admin → Radio**: **Load starter list**, verify each frequency on
   RadioReference, turn on the ones you want, **Apply**.
2. Stop OpenWebRX so the recorder can use the dongle, and keep it from restarting:

   ```bash
   docker stop owrx && docker update --restart=no owrx
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
| Tunnel logs | `cd /opt/hawksroost && docker compose logs --tail=20 cloudflared` |
| Restart everything | `cd /opt/hawksroost && docker compose restart` |
| Admin invite link | `bash /opt/hawksroost/scripts/admin-invite.sh` |
| Password reset link | `cd /opt/hawksroost && docker compose exec api python -m app.cli reset-link someone@example.com` |
