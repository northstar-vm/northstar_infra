# northstar-infra

Private infrastructure templates for the `northstar` Oracle VM. This repo manages server/proxy/admin tooling only; the deployed app code stays in `cruetto/IndividualTeacher`.

## VM

- Name: `northstar`
- Region: Germany Central / Frankfurt
- Public IP: `130.61.33.233`
- SSH user: `ubuntu`
- Shape: `VM.Standard.A1.Flex`, 4 OCPU, 24 GB RAM
- Boot disk: about 200 GB
- Server root: `/opt/northstar`
- Infra repo on VM: `/opt/northstar/infra`
- Active Caddy proxy folder: `/opt/northstar/infra/proxy`
- Existing Quizzy app: `/opt/northstar/apps/quizzy`
- CV / portfolio app: `/opt/northstar/apps/cv`
- Minecraft server data: `/opt/northstar/apps/minecraft/data`
- Quizzy domain: `https://quizzy.attentionisallineed.xyz`
- CV domain: `https://cv.attentionisallineed.xyz`
- Admin portal domain: `https://northstar.attentionisallineed.xyz`
- Minecraft address: `mc.attentionisallineed.xyz`
- Root domain: `https://attentionisallineed.xyz`, redirects to CV

## Existing App

Quizzy / IndividualTeacher is already deployed from the app repo:

```text
cruetto/IndividualTeacher
```

Current app details:

- Compose services: `backend`, `frontend`, `mongo`, `web`
- Backend runs in Docker on port `5000`
- Frontend runs in Docker/nginx on port `80`
- App `web`/nginx is `quizzy-web-1` and joins the shared `northstar_web` network
- MongoDB runs in the Quizzy app stack as `quizzy-mongo-1`, bound to `127.0.0.1:27017` for maintenance only
- Caddy proxies `quizzy.attentionisallineed.xyz` to `quizzy-web-1:80`

Keep that working Caddy route intact when adding the northstar admin route.

## Portfolio / CV App

The CV site is deployed from:

```text
cruetto/PortfolioWebsite
```

It is served as a static Nginx site from:

```text
/opt/northstar/apps/cv
```

Public URL:

```text
https://cv.attentionisallineed.xyz
```

Deploy target:

- The script `/opt/northstar/infra/scripts/deploy-cv.sh` updates `/opt/northstar/apps/cv` and restarts the CV Nginx container.

## What This Adds

- `https://northstar.attentionisallineed.xyz/` - static admin portal page
- `https://northstar.attentionisallineed.xyz/files/` - File Browser
- `https://northstar.attentionisallineed.xyz/status/api` - private VM, Docker, Minecraft, and history API used by the admin portal

The admin domain is protected with Caddy Basic Auth. Caddy routes are tracked in `proxy/Caddyfile`, while secrets live in the ignored VM-only `proxy/.env`. File Browser relies on the Caddy login only.

The portal home page shows VM CPU/RAM/disk, Docker container CPU/RAM/disk stats with safe start/stop/restart/pause controls, Minecraft backup count/size with a `Backup now` button, and Minecraft player history plus a live Server-Sent Events console/log stream. Player profiles store nickname, UUID when available, first seen, last seen, join count, leave count, and last action. The status API stores 10 days of samples in SQLite under `/opt/northstar/admin/status-data` and is not published directly to the internet.

Portainer has been removed. Use the built-in Docker panel for common actions, and SSH for anything dangerous or unusual.

## CI/CD

GitHub Actions deploy is active in `.github/workflows/deploy.yml`:

- Pushes to `main` automatically run `/opt/northstar/infra/scripts/deploy-infra.sh` on the VM.
- The workflow can also be run manually from the GitHub Actions tab.

Add these repository secrets in GitHub before using deploy:

```text
NORTHSTAR_HOST=130.61.33.233
NORTHSTAR_USER=ubuntu
NORTHSTAR_SSH_KEY=<private deploy key with access to the VM>
```

Automatic deploy uses these secrets to SSH into the VM.

## File Browser Scope

File Browser is configured to expose one upload/download folder:

```text
/opt/northstar/admin/files
```

Inside File Browser this appears as the root folder:

```text
/
```

This keeps browser-based file management away from system directories and should avoid drag-and-drop failures caused by uploading into root-owned paths. Keep File Browser reachable only through the Caddy-protected northstar domain.

## Minecraft Java Server

The Minecraft server is a Dockerized Paper Java Edition server. Its compose file lives in:

```text
apps/minecraft/docker-compose.yml
```

Runtime server data lives outside the infra repo in:

```text
/opt/northstar/apps/minecraft/data
```

Create the VM-only environment file before first start:

```bash
cd /opt/northstar/infra/apps/minecraft
cp .env.example .env
nano .env
```

Set `OPS` to the exact Minecraft Java username that should have operator/admin permissions, or leave it blank for first boot. Minecraft currently runs with `ONLINE_MODE=FALSE`, so keep AuthMe and SimpleWhitelist installed in `/opt/northstar/apps/minecraft/data/plugins` before opening the server to players.

Current offline-mode safety layer:

- AuthMe requires players to register and log in with a password.
- SimpleWhitelist allows only configured player names.
- Vanilla `white-list` should stay off in `server.properties`; SimpleWhitelist owns the name-based whitelist.

During first setup, the compose file uses `restart: "no"` so configuration errors do not create a restart loop. After the server is stable, switch it back to `restart: unless-stopped` if you want it to auto-start after VM or Docker restarts.

Start and inspect the server on the VM:

```bash
cd /opt/northstar/infra/apps/minecraft
docker compose up -d
docker compose logs -f minecraft
```

The general infra deployment script also starts Minecraft if `/opt/northstar/infra/apps/minecraft/.env` exists:

```bash
bash /opt/northstar/infra/scripts/deploy-infra.sh
```

Create a manual world backup on the VM:

```bash
bash /opt/northstar/infra/scripts/backup-minecraft.sh
```

The script uses `sudo tar` so it can read all server-owned world files. For unattended cron backups, allow the `ubuntu` user to run tar without a password:

```bash
echo 'ubuntu ALL=(root) NOPASSWD: /usr/bin/tar' | sudo tee /etc/sudoers.d/northstar-minecraft-backup
sudo chmod 440 /etc/sudoers.d/northstar-minecraft-backup
sudo visudo -cf /etc/sudoers.d/northstar-minecraft-backup
```

Backups are written to:

```text
/opt/northstar/backups/minecraft
```

The admin portal also shows the Minecraft backup summary: total stored size, backup count, recent files, dates, and per-file MB. As of 2026-05-20, the panel showed 11 backup files stored using about 2.3 GiB total, with recent archives around 217-221 MiB each.

To run backups every 8 hours, install this cron entry on the VM with `crontab -e`:

```cron
0 */8 * * * /bin/bash /opt/northstar/infra/scripts/backup-minecraft.sh >> /opt/northstar/backups/minecraft/backup.log 2>&1
```

Players connect to:

```text
mc.attentionisallineed.xyz
```

Minecraft uses raw TCP on port `25565`, not HTTP/HTTPS, so it does not go through Caddy.

## Secrets

Do not commit real passwords, Caddy hashes, File Browser databases, status SQLite databases, or runtime volumes.

Also do not commit API keys, private SSH keys, MongoDB connection strings, Google OAuth secrets, or real VM-only config.

Generate a Caddy Basic Auth hash on the VM:

```bash
docker run --rm caddy:2 caddy hash-password --plaintext 'replace-this-password'
```

Then put the resulting hash only in the real VM `proxy/.env` as `ADMIN_PASSWORD_HASH`.

## Cloudflare

Cloudflare manages DNS for `attentionisallineed.xyz`. Hostinger is only the registrar, with nameservers set to:

- `kay.ns.cloudflare.com`
- `lex.ns.cloudflare.com`

Create these DNS records:

| Type | Name | Content | Proxy |
| --- | --- | --- | --- |
| `A` | `attentionisallineed.xyz` | `130.61.33.233` | Enabled |
| `A` | `cv` | `130.61.33.233` | Enabled |
| `A` | `northstar` | `130.61.33.233` | Enabled |
| `A` | `quizzy` | `130.61.33.233` | Enabled |
| `A` | `mc` | `130.61.33.233` | Disabled / DNS-only |
| `CNAME` | `www` | `attentionisallineed.xyz` | Enabled |

`attentionisallineed.xyz`, `www`, `quizzy`, `cv`, and `northstar` can all be Cloudflare proxied while Caddy is serving valid HTTPS certificates on the VM. If Cloudflare shows a TLS error, check Cloudflare SSL/TLS mode before changing the VM.

Keep `mc.attentionisallineed.xyz` DNS-only because Cloudflare's normal orange-cloud proxy does not proxy Minecraft TCP traffic.

## External Services

MongoDB for Quizzy:

- Production MongoDB runs inside the Quizzy app repo Compose stack.
- It is not routed through Caddy, Cloudflare, or Oracle public ingress.
- Atlas may remain only as rollback/migration history; do not send new production embeddings there after VM-local MongoDB is verified.

Google OAuth for Quizzy:

- Authorized JavaScript origin: `https://quizzy.attentionisallineed.xyz`
- Authorized redirect URI: `https://quizzy.attentionisallineed.xyz/api/auth/google/callback`

Oracle cost guardrails:

- A1 quota: `standard-a1-core-count` set to `4`
- A1 memory quota: `standard-a1-memory-count` set to `24`
- A2 quotas set to `0`
- Budget alert enabled
