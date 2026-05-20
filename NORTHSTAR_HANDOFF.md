# Northstar Handoff Context

Use this file as the first message/context for a new chat. It summarizes the current Oracle VM, domains, repos, Docker layout, CI/CD, and known loose ends.

## Goal

The user is hosting multiple personal/project services on one Oracle Cloud VM named `northstar`:

- `quizzy.attentionisallineed.xyz` - current Quizzy / IndividualTeacher frontend and backend.
- `cv.attentionisallineed.xyz` - static CV / portfolio website.
- `northstar.attentionisallineed.xyz` - private admin portal with Docker and file-manager tools.
- `mc.attentionisallineed.xyz` - Minecraft Java Edition Paper server.
- `attentionisallineed.xyz` - root domain should redirect to CV, or otherwise be handled by Caddy.

The user wants to keep this cheap/free-tier friendly, organized, Docker-based, and easy to manage through GitHub Actions where reasonable.

## Important Style / Collaboration Notes

- The user is learning deployment and cloud infrastructure while doing it. Give concrete commands and explain why, but do not overcomplicate.
- Prefer step-by-step instructions with verification commands.
- Before deleting or moving server files, inspect first and use backup/archive moves instead of destructive deletion.
- Never ask the user to put private keys, passwords, MongoDB URI, OAuth secrets, or Caddy hashes into public repos.
- When giving local-machine commands versus VM commands, label them clearly. The user previously accidentally ran local cleanup commands on the VM.

## Oracle VM

- Provider: Oracle Cloud Infrastructure.
- Instance name: `northstar`.
- Region: Germany Central / Frankfurt, `eu-frankfurt-1`.
- Public IPv4: `130.61.33.233`.
- OS: Ubuntu 22.04.
- SSH user: `ubuntu`.
- Shape: `VM.Standard.A1.Flex`.
- Resources: 4 OCPU, 24 GB RAM.
- Boot disk: about 200 GB.
- Main server root: `/opt/northstar`.

SSH pattern:

```bash
ssh -i ssh-key-2026-05-15.key ubuntu@130.61.33.233
```

Do not expose the private SSH key.

## DNS / Cloudflare / Hostinger

Domain:

```text
attentionisallineed.xyz
```

Registrar:

```text
Hostinger
```

DNS provider:

```text
Cloudflare
```

Cloudflare nameservers set at Hostinger:

```text
kay.ns.cloudflare.com
lex.ns.cloudflare.com
```

Current relevant Cloudflare DNS records:

```text
A      attentionisallineed.xyz  130.61.33.233  Proxied
A      cv                       130.61.33.233  Proxied
A      mc                       130.61.33.233  DNS only
A      northstar                130.61.33.233  Proxied
A      quizzy                   130.61.33.233  Proxied
CNAME  www                      attentionisallineed.xyz  Proxied
```

If Cloudflare shows TLS errors, check Cloudflare SSL/TLS mode and Caddy logs before changing DNS randomly.

Important: `mc` must stay DNS-only / gray-cloud. Minecraft uses raw TCP on port `25565`; it does not go through the normal Cloudflare HTTP proxy or Caddy.

## Oracle Network / Firewall

OCI ingress rules added:

- TCP 22 for SSH.
- TCP 80 for HTTP.
- TCP 443 for HTTPS.
- TCP 25565 for Minecraft Java Edition.

Ubuntu `ufw` was inactive earlier, but rules were added:

```bash
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 25565/tcp
sudo ufw status
```

Check current firewall state before changing it:

```bash
sudo ufw status verbose
```

## Repos

Main app repo:

```text
https://github.com/northstar-vm/quizzy
```

Infra repo:

```text
https://github.com/northstar-vm/northstar_infra
```

CV repo:

```text
https://github.com/cruetto/PortfolioWebsite
```

## VM Directory Layout

Current observed `/opt/northstar` layout:

```text
/opt/northstar
├── admin
│   └── files
├── apps
│   ├── cv
│   ├── minecraft
│   └── quizzy
├── backups
│   └── minecraft
├── infra
└── proxy   # old proxy folder; should be archived if not already moved
```

Preferred final layout:

```text
/opt/northstar
├── admin
│   └── files
├── apps
│   ├── cv
│   ├── minecraft
│   └── quizzy
├── backups
│   └── minecraft
└── infra
```

The old top-level `/opt/northstar/proxy` is stale because active Caddy now runs from:

```text
/opt/northstar/infra/proxy
```

Safe archive command, only after confirming active Caddy is running from infra:

```bash
cd /opt/northstar
mv proxy backups/proxy-old-before-infra-cleanup
```

## Docker Layout

Check running containers:

```bash
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}"
```

Expected important containers:

```text
northstar-caddy         caddy:2
northstar-cv-web        nginx:1.27-alpine
northstar-filebrowser   filebrowser/filebrowser:latest
northstar-minecraft     itzg/minecraft-server:java25
northstar-status        python:3.13-alpine
quizzy-backend-1        quizzy-backend
quizzy-frontend-1       quizzy-frontend
quizzy-mongo-1          mongodb/mongodb-atlas-local:latest
quizzy-web-1            nginx:1.27-alpine
```

Shared external Docker network:

```text
northstar_web
```

Create if missing:

```bash
docker network create northstar_web || true
```

## Active Services

### Caddy

Active folder:

```bash
cd /opt/northstar/infra/proxy
```

Tracked Caddyfile:

```text
/opt/northstar/infra/proxy/Caddyfile
```

Important: `proxy/Caddyfile` is tracked and uses environment placeholders. Real VM-only values live in:

```text
/opt/northstar/infra/proxy/.env
```

Required env values:

```text
CADDY_EMAIL=...
ADMIN_USERNAME=vallutto
ADMIN_PASSWORD_HASH=...
QUIZZY_UPSTREAM=...
```

Reload Caddy:

```bash
cd /opt/northstar/infra/proxy
docker compose exec -T caddy caddy reload --config /etc/caddy/Caddyfile
```

View logs:

```bash
cd /opt/northstar/infra/proxy
docker compose logs --tail=120 caddy
```

### Quizzy

App folder:

```bash
cd /opt/northstar/apps/quizzy
```

Compose:

```bash
docker compose ps
docker compose logs --tail=80 backend
docker compose logs --tail=80 frontend
docker compose logs --tail=80 web
```

Public URL:

```text
https://quizzy.attentionisallineed.xyz
```

Health/test commands:

```bash
curl -I https://quizzy.attentionisallineed.xyz
curl -i https://quizzy.attentionisallineed.xyz/api/quizzes?scope=public
```

Expected:

- Frontend returns HTTP 200.
- `/api/quizzes?scope=public` returns JSON.
- `/api/` may return 404; that is not necessarily a backend failure.

### CV / Portfolio

App folder:

```bash
cd /opt/northstar/apps/cv
```

Public URL:

```text
https://cv.attentionisallineed.xyz
```

Compose file lives in infra:

```bash
cd /opt/northstar/infra/apps/cv
docker compose ps
docker compose up -d
```

Test:

```bash
curl -I https://cv.attentionisallineed.xyz
curl -s "https://cv.attentionisallineed.xyz/javascript/main.js?v=$(date +%s)" | grep -n "helloSubtitle"
```

### Minecraft Java Server

Public address:

```text
mc.attentionisallineed.xyz
```

Service:

```text
Minecraft Java Edition, Paper, Dockerized with itzg/minecraft-server:java25
```

Important runtime choices:

- Compose file: `/opt/northstar/infra/apps/minecraft/docker-compose.yml`.
- VM-only env file: `/opt/northstar/infra/apps/minecraft/.env`.
- World/server data: `/opt/northstar/apps/minecraft/data`.
- Backups: `/opt/northstar/backups/minecraft`.
- Port: `25565/tcp`, published directly by Docker.
- `online-mode=false`; AuthMe handles player registration/login.
- SimpleWhitelist handles name-based whitelist through `/whitelist` commands.
- MOTD is managed directly in compose as a YAML multiline value; the VM-only `.env` should not set `SERVER_NAME`.
- RCON is available inside the container for `docker exec ... rcon-cli`, but port `25575` is not published to the internet.
- Current compose uses `restart: "no"` to avoid restart loops during setup/debugging. Once stable, it can be changed to `restart: unless-stopped`.

Start / inspect:

```bash
cd /opt/northstar/infra/apps/minecraft
docker compose up -d
docker compose ps
docker compose logs -f minecraft
```

Stop following logs without stopping the server:

```text
Ctrl+C
```

Stop the server:

```bash
cd /opt/northstar/infra/apps/minecraft
docker compose down
```

Make a player operator:

```bash
docker exec -i northstar-minecraft rcon-cli op YourMinecraftUsername
```

Check whether the port is published:

```bash
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep minecraft
```

Expected port includes:

```text
0.0.0.0:25565->25565/tcp
```

Backups:

```bash
bash /opt/northstar/infra/scripts/backup-minecraft.sh
ls -lh /opt/northstar/backups/minecraft
```

Backup behavior:

- Backups are full compressed `.tar.gz` archives, not incremental.
- Script tells the server `save-off`, `save-all flush`, archives the data folder, then `save-on`.
- Script uses `sudo tar` because some container-owned files are not readable by plain `ubuntu`.
- Default retention is 7 days.
- The admin portal has a Backups panel showing total stored size, backup count, recent archive filenames, dates, per-file MB, and a `Backup now` button.
- Observed on 2026-05-20: 11 backup files stored, about 2.3 GiB total, with recent archives around 217-221 MiB each.
- Recommended cron schedule is every 8 hours, about 21 backups total:

```cron
0 */8 * * * /bin/bash /opt/northstar/infra/scripts/backup-minecraft.sh >> /opt/northstar/backups/minecraft/backup.log 2>&1
```

Cron needs this sudoers rule for unattended backups:

```bash
echo 'ubuntu ALL=(root) NOPASSWD: /usr/bin/tar' | sudo tee /etc/sudoers.d/northstar-minecraft-backup
sudo chmod 440 /etc/sudoers.d/northstar-minecraft-backup
sudo visudo -cf /etc/sudoers.d/northstar-minecraft-backup
```

If stopping Minecraft for a long time, make one final backup, stop the container, and comment out the cron line. Otherwise cron will keep creating repeated backups of the same stopped world and will still delete archives older than the retention window.

### Admin Portal

Public/private URL:

```text
https://northstar.attentionisallineed.xyz
```

It is protected by Caddy Basic Auth. Expected anonymous status:

```bash
curl -I https://northstar.attentionisallineed.xyz
```

Expected:

```text
HTTP/2 401
```

Routes:

```text
/          static admin portal
/files/    File Browser
/status/api private JSON status for portal CPU/RAM/disk bars, Docker controls, Minecraft backups, and Minecraft panel
```

Admin compose:

```bash
cd /opt/northstar/infra/admin
docker compose ps
docker compose logs --tail=80 filebrowser
docker compose logs --tail=40 status
```

The portal homepage shows VM CPU/RAM/disk usage, Docker container stats, allowlisted Docker actions, a Minecraft backups panel, expandable live Docker logs, and a Minecraft panel with player count, persisted player history, and a live Server-Sent Events console/log stream. Static HTML cannot read VM stats directly, so `admin/docker-compose.yml` runs a small internal `northstar-status` container from `admin/status/status_server.py`.
Player profiles in SQLite store nickname, UUID when available from logs, first seen, last seen, join count, leave count, and last action.

Status service design:

- Mounts `/` and `/proc` read-only for VM stats.
- Mounts `/var/run/docker.sock` for Docker stats and allowlisted start/stop/restart/pause actions.
- Serves full allowlisted Docker logs to the portal at `/status/docker/logs?container=...`.
- Reads `/opt/northstar/backups/minecraft` through the `/backups/minecraft` mount and exposes backup summary plus manual backup creation at `/status/minecraft/backup`.
- Stores 10 days of SQLite history in `/opt/northstar/admin/status-data/northstar.db`.
- Reads Minecraft raw logs through Docker logs for `northstar-minecraft`.
- Streams Minecraft logs to the portal through `/status/minecraft/logs/stream` using Server-Sent Events.
- Sends Minecraft panel commands through `docker exec ... mc-send-to-console`, with `rcon-cli` fallback, never through a shell.
- Minecraft compose sets `CREATE_CONSOLE_IN_PIPE=TRUE`; it applies after the next intentional Minecraft restart/recreate.
- Queries Minecraft through the normal server-list ping on `northstar-minecraft:25565`.
- Exposes only container port `8080` on the Docker network.
- Caddy proxies `/status/*` behind the existing northstar Basic Auth.

Infra deployment:

- Every push to `northstar-vm/northstar_infra` `main` runs GitHub Actions and then `/opt/northstar/infra/scripts/deploy-infra.sh` on the VM.
- The deploy script force-recreates admin, CV, and proxy/Caddy services so frontend and Python changes take effect immediately.
- Minecraft is intentionally left running with `docker compose up -d --no-recreate`; restart it manually from `/opt/northstar/infra/apps/minecraft` when needed.

Manual status checks on the VM:

```bash
free -h
df -h /
cd /opt/northstar/infra/admin
docker compose exec status python -c "import json, urllib.request; print(json.dumps(json.load(urllib.request.urlopen('http://127.0.0.1:8080/api')), indent=2))"
```

## File Browser

File Browser is configured for one safe upload/download folder:

```text
Host /opt/northstar/admin/files -> Container /srv
```

The container runs as the VM `ubuntu` UID/GID and stores File Browser database/config files under:

```text
/opt/northstar/admin/filebrowser
```

Inside File Browser, `/opt/northstar/admin/files` appears as:

```text
/
```

File Browser uses `--noauth` and relies on the northstar Caddy Basic Auth gateway instead of its own login screen. If drag-and-drop uploads fail, fix the host folder permissions:

```bash
sudo mkdir -p /opt/northstar/admin/files
sudo mkdir -p /opt/northstar/admin/filebrowser/database /opt/northstar/admin/filebrowser/config
sudo chown -R ubuntu:ubuntu /opt/northstar/admin/files /opt/northstar/admin/filebrowser
sudo chmod 775 /opt/northstar/admin/files
sudo chmod -R u+rwX,g+rwX /opt/northstar/admin/files
```

After changing from the old whole-VM mount, recreate the File Browser container:

```bash
cd /opt/northstar/infra/admin
docker compose stop filebrowser
docker compose rm -f filebrowser
sudo mkdir -p /opt/northstar/admin/filebrowser/database /opt/northstar/admin/filebrowser/config
sudo chown -R ubuntu:ubuntu /opt/northstar/admin/files /opt/northstar/admin/filebrowser
docker compose up -d filebrowser
```

## Old Portainer Cleanup

Portainer has been removed in favor of the built-in portal Docker panel. If the old container or volume still exists, remove only Portainer's UI data:

```bash
cd /opt/northstar/infra/admin
docker rm -f northstar-portainer
docker volume rm admin_portainer_data
```

## SSH Keys / Secrets

Best places:

```text
/home/ubuntu/.ssh/          SSH keys for git/server access
/opt/northstar/secrets/     app/deployment-only secrets
```

Create secrets folder:

```bash
sudo mkdir -p /opt/northstar/secrets
sudo chown root:ubuntu /opt/northstar/secrets
sudo chmod 750 /opt/northstar/secrets
```

SSH key permissions:

```bash
chmod 700 /home/ubuntu/.ssh
chmod 600 /home/ubuntu/.ssh/private_key_name
chmod 644 /home/ubuntu/.ssh/private_key_name.pub
```

Do not store private keys inside git repos:

```text
/opt/northstar/infra
/opt/northstar/apps/quizzy
/opt/northstar/apps/cv
```

## GitHub / Deploy Keys / CI-CD

The VM can pull `northstar_infra` via SSH deploy key.

Test on VM:

```bash
ssh -T git@github.com
```

For the infra repo:

```bash
cd /opt/northstar/infra
git remote -v
git pull --ff-only
```

GitHub Actions for CV:

- Repo: `cruetto/PortfolioWebsite`.
- Workflow: `.github/workflows/deploy-cv.yml`.
- It runs on pushes to `main`.
- It SSHes to the VM and runs:

```bash
bash /opt/northstar/infra/scripts/deploy-cv.sh
```

Required GitHub secrets in `PortfolioWebsite`:

```text
NORTHSTAR_HOST=130.61.33.233
NORTHSTAR_USER=ubuntu
NORTHSTAR_SSH_KEY=<private SSH key authorized on VM>
```

Workflow template also exists in infra repo:

```text
/opt/northstar/infra/github-actions-templates/deploy-cv.yml
```

It is okay to keep templates in infra. They are not runtime code.

## Git Ignore / VM-only Files

Infra repo should ignore real runtime secrets/configs:

```gitignore
.env
.env.*
secrets/
*.key
*.pem
*.crt
northstar_actions
northstar_actions.pub
proxy/.env
apps/minecraft/.env
apps/minecraft/data/
```

On VM, this is good:

```bash
cd /opt/northstar/infra
git status --short --ignored
```

Expected:

```text
!! proxy/.env
```

That means real Caddy secret values are ignored correctly.

Minecraft VM-only runtime files should also be ignored:

```text
apps/minecraft/.env
apps/minecraft/data/
```

The real Minecraft world data lives at `/opt/northstar/apps/minecraft/data`, not inside the infra repo.

## Local Linux Minecraft Client

The user plays from Linux and uses SKLauncher through a Firejail sandbox.

Local launcher/security setup:

- Wrapper: `/home/vallutto/.local/bin/minecraft-secure`.
- Desktop shortcut: `/home/vallutto/Desktop/Minecraft-Secure.desktop`.
- Sandbox/private home: `/home/vallutto/.safe-minecraft`.
- Launcher jar: `/home/vallutto/.safe-minecraft/SKlauncher-3.2.18.jar`.
- Java: `/usr/lib/jvm/java-25-openjdk-amd64/bin/java`.
- GPU: NVIDIA PRIME offload env vars are set in the wrapper.

The wrapper intentionally keeps SKLauncher/Minecraft inside the Firejail private home so it does not casually access the user's normal home files.

Useful local checks:

```bash
~/.local/bin/minecraft-secure
nvidia-smi
java -version
```

In Minecraft F3, the client was confirmed to show:

```text
Sodium Renderer
ImmediatelyFast
Java 25
NVIDIA GeForce RTX 3050 Ti
Fabric 26.1.2
```

Client mods live inside the sandbox:

```text
/home/vallutto/.safe-minecraft/.minecraft/mods
```

Recommended client-side performance stack already discussed:

- Sodium.
- ImmediatelyFast.
- Entity Culling.
- FerriteCore.
- Dynamic FPS.
- Fabric API when required.

Iris is optional and mainly for shaders; it is not needed for performance.

## MongoDB

Quizzy production MongoDB runs inside the IndividualTeacher app Compose stack as `quizzy-mongo-1`.

The infra repo owns only the shared network and Caddy route. Do not add a Caddy route, Cloudflare DNS record, or Oracle public ingress rule for MongoDB.

Atlas project `Quizzy` / cluster `Cluster0` may remain as rollback or migration history, but new production embeddings should go to the VM-local MongoDB.

## Google OAuth

For Quizzy production domain:

Authorized JavaScript origin:

```text
https://quizzy.attentionisallineed.xyz
```

Authorized redirect URI:

```text
https://quizzy.attentionisallineed.xyz/api/auth/google/callback
```

Earlier error:

```text
Error 400: origin_mismatch
```

Cause: Google OAuth origins/redirects not matching deployed domain.

## Oracle Cost Guardrails

The user upgraded to Pay As You Go but wants Always Free guardrails.

Oracle quota policies were configured so A1 stays within free tier-ish usage:

```text
standard-a1-core-count   4
standard-a1-memory-count 24
standard-a2-core-count   0
standard-a2-memory-count 0
```

Exact Oracle quota names vary; user eventually got policy working. Be careful before changing quotas.

Also budget alerts were enabled.

## Important Current Loose Ends

### 1. CV Browser Not Visually Updating

Server has proven updated code:

```bash
cd /opt/northstar/apps/cv
git log -1 --oneline
grep -n "Junior AI Engineer" javascript/main.js
curl -s "https://cv.attentionisallineed.xyz/javascript/main.js?v=$(date +%s)" | grep "Junior AI Engineer"
```

This showed:

```text
helloSubtitle: { en: "Junior AI Engineer & Problem Solver", lt: "DI Sistemų Studentas ir Problemų Sprendėjas" },
```

So the VM and public JS were updated.

Possible causes:

- Browser/site language is Lithuanian, so it shows the `lt` string, not the changed `en` string.
- Browser is opening old GitHub Pages/Vercel URL instead of `https://cv.attentionisallineed.xyz`.
- Static asset cache.
- JavaScript/localStorage language preference.

Do not hardcode dates into app code as a cache fix unless intentionally using a build-generated asset hash.

Better next checks:

```bash
curl -s "https://cv.attentionisallineed.xyz/" | grep -n "main.js"
curl -s "https://cv.attentionisallineed.xyz/javascript/main.js?v=$(date +%s)" | grep -n "helloSubtitle"
```

Browser console reset:

```js
localStorage.clear()
location.reload()
```

If editing CV, update both translations:

```js
helloSubtitle: {
  en: "Junior AI Engineer & Problem Solver",
  lt: "Jaunesnysis DI inžinierius ir problemų sprendėjas"
}
```

### 2. Root Domain

Root DNS now points to VM:

```text
A attentionisallineed.xyz 130.61.33.233 Proxied
```

Caddy should have a block for root domain. Suggested behavior:

```caddy
attentionisallineed.xyz {
	redir https://cv.attentionisallineed.xyz{uri}
}

www.attentionisallineed.xyz {
	redir https://cv.attentionisallineed.xyz{uri}
}
```

Reload Caddy after editing:

```bash
cd /opt/northstar/infra/proxy
docker compose exec -T caddy caddy reload --config /etc/caddy/Caddyfile
```

Test:

```bash
curl -I https://attentionisallineed.xyz
curl -I https://www.attentionisallineed.xyz
```

Expected: redirect to CV.

### 3. Old Proxy Folder

If not already archived:

```bash
cd /opt/northstar
mv proxy backups/proxy-old-before-infra-cleanup
```

Only do this after confirming active Caddy container is from `/opt/northstar/infra/proxy`.

## Useful VM Commands

Tree:

```bash
cd /opt/northstar
tree -L 4
```

Disk:

```bash
df -h
du -h --max-depth=2 /opt/northstar | sort -h
```

RAM/CPU:

```bash
free -h
top
```

Docker usage:

```bash
docker ps
docker stats
docker system df
```

Compose status:

```bash
cd /opt/northstar/infra/proxy && docker compose ps
cd /opt/northstar/infra/admin && docker compose ps
cd /opt/northstar/infra/apps/cv && docker compose ps
cd /opt/northstar/apps/quizzy && docker compose ps
```

Site checks:

```bash
curl -I https://quizzy.attentionisallineed.xyz
curl -I https://cv.attentionisallineed.xyz
curl -I https://northstar.attentionisallineed.xyz
curl -I https://attentionisallineed.xyz
```

Expected:

- Quizzy: `200`.
- CV: `200`.
- Northstar without auth: `401`.
- Root: redirect to CV if Caddy root block is configured.

## What Not To Do

- Do not commit real `proxy/.env`.
- Do not commit private SSH keys.
- Do not commit real `.env` files.
- Do not expose Docker socket publicly.
- Do not expose Quizzy MongoDB publicly through Caddy, Cloudflare, or Oracle ingress.
- Do not delete `/opt/northstar/proxy`; archive it first.
- Do not broaden File Browser back to the whole VM unless you intentionally accept the extra risk.
