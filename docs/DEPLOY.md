# Deploy and run on the cabin laptop

Everything runs from `/opt/hawksroost` on the Dell Latitude (Debian, Docker),
over SSH. Integrations (cameras, Tempest, Starlink, email, Google sign-in, radio
channels, sign-in photo) are set up in the app afterwards, under
**Admin → Integrations** and **Admin → Radio** — not on the server.

## Overview

1. Give the laptop read-only access to the private GitHub repo (a deploy key).
2. Put the code in `/opt/hawksroost`.
3. Check the laptop (read-only script).
4. Battery charge limit in the Dell BIOS.
5. Create the Cloudflare tunnel; copy its token.
6. Run the installer (asks for the token, builds, starts).
7. Make the first admin account.
8. In the app: add the camera, check Tempest and Starlink, set up email and Google.
9. Last: the radio.

---

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

## 3. Check the laptop

Read-only; changes nothing; takes about 2 minutes (it listens 70 seconds for the Tempest hub):

```bash
bash /opt/hawksroost/scripts/inventory.sh
```

Paste the output back to Claude.

## 4. Battery charge limit

An always-plugged-in laptop battery swells if it sits at 100%. In the Dell BIOS
(F2 at boot): **Power → Primary Battery Charge Configuration → Primarily AC use**
(or Custom, 50–80%). Menu names vary by model.

## 5. Cloudflare tunnel

In the Cloudflare dashboard (hawksroost.live is on Cloudflare DNS):

1. **Zero Trust → Networks → Tunnels** (some accounts show **Networks → Connectors**) → **Create a tunnel** → **Cloudflared**.
2. Name it `hawksroost`. On the install screen pick **Docker**; the command shown ends in a long token after `--token`. Copy just the token.
3. Add a **public hostname / published application route**: subdomain blank, domain `hawksroost.live`, service type **HTTP**, URL `web:80`.

Menu names change often; what matters is the token and the route to `http://web:80`.

## 6. Install

Asks for the token (paste, Enter — it won't show), builds, and starts everything:

```bash
cd /opt/hawksroost && bash scripts/install.sh
```

Success ends with `OK: app is up` and a list of running services. Then
`https://hawksroost.live` shows the sign-in page. On the cabin network it's
also at `http://<laptop-ip>:8080`.

## 7. First admin

Prints a one-time link (good for 2 days):

```bash
bash /opt/hawksroost/scripts/admin-invite.sh
```

Open it, create your account. Everyone else: **Admin → People → Invite**.

## 8. Integrations (in the app)

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
| Tunnel logs | `cd /opt/hawksroost && docker compose logs --tail=20 cloudflared` |
| Restart everything | `cd /opt/hawksroost && docker compose restart` |
| Admin invite link | `bash /opt/hawksroost/scripts/admin-invite.sh` |
| Password reset link | `cd /opt/hawksroost && docker compose exec api python -m app.cli reset-link someone@example.com` |
