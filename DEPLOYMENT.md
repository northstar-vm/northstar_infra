# Deployment

These steps assume you are SSH'd into the VM as `ubuntu`.

This repo is the separate private GitHub repo for northstar VM infrastructure. Do not place these files inside `/opt/northstar/apps/quizzy` or the `northstar-vm/quizzy` app repo.

## CI/CD

GitHub Actions deploys the repo directly.

- `Deploy Infra`: runs automatically on push to `main`.
- The same workflow can also be run manually from GitHub Actions.

Create these GitHub repository secrets before running deploy:

```text
NORTHSTAR_HOST=130.61.33.233
NORTHSTAR_USER=ubuntu
NORTHSTAR_SSH_KEY=<private deploy key with access to the VM>
```

Normal update flow:

```bash
git add .
git commit -m "Describe the change"
git push
```

After pushing to `main`, GitHub Actions SSHes into the VM and runs `/opt/northstar/infra/scripts/deploy-infra.sh`. The script force-recreates admin, CV, and proxy/Caddy services so code and static file changes take effect immediately. Minecraft is intentionally not recreated by CI; restart it manually when needed.

## 1. Prepare Folders

```bash
sudo mkdir -p /opt/northstar/infra
sudo mkdir -p /opt/northstar/admin/portal
sudo mkdir -p /opt/northstar/admin/files
sudo mkdir -p /opt/northstar/admin/filebrowser/database
sudo mkdir -p /opt/northstar/admin/filebrowser/config
sudo mkdir -p /opt/northstar/admin/status-data
sudo mkdir -p /opt/northstar/apps/minecraft/data
sudo mkdir -p /opt/northstar/backups
sudo chown -R ubuntu:ubuntu /opt/northstar/admin
sudo chown -R root:root /opt/northstar/admin/status-data
sudo chown -R ubuntu:ubuntu /opt/northstar/apps/minecraft
sudo chown -R ubuntu:ubuntu /opt/northstar/backups
sudo chmod 775 /opt/northstar/admin/files
```

This repo is cloned to `/opt/northstar/infra`. App source repositories live separately in `/opt/northstar/apps`.

Expected layout:

```text
/opt/northstar/
  infra/
    admin/
      docker-compose.yml
      portal/
        index.html
    apps/
      cv/
        docker-compose.yml
      minecraft/
        docker-compose.yml
        .env.example
    proxy/
      docker-compose.yml
      Caddyfile
  apps/
    quizzy/
    cv/
    minecraft/
      data/
  backups/
```

## 2. Create the Admin Docker Network

The proxy and admin services communicate on a shared Docker network:

```bash
docker network create northstar_web
```

If it already exists, Docker will say so; that is fine.

## 3. Deploy the CV Site

Clone the portfolio website into the apps directory:

```bash
sudo mkdir -p /opt/northstar/apps
sudo chown -R ubuntu:ubuntu /opt/northstar/apps

cd /opt/northstar/apps
git clone https://github.com/cruetto/PortfolioWebsite.git cv
```

Start the CV Nginx service from this infra repo:

```bash
cd /opt/northstar/infra/apps/cv
docker compose up -d
```

To update the CV site later:

```bash
cd /opt/northstar/apps/cv
git pull

cd /opt/northstar/infra/apps/cv
docker compose up -d
```

Or use the deployment script:

```bash
bash /opt/northstar/infra/scripts/deploy-cv.sh
```

## 4. Start the Minecraft Java Server

Minecraft runs as a Paper Java Edition server from this infra repo, with the world data stored outside git at `/opt/northstar/apps/minecraft/data`.

During first setup, the compose file uses `restart: "no"` so configuration errors do not create a restart loop. After the server is stable, switch it back to `restart: unless-stopped` if you want it to auto-start after VM or Docker restarts.

First, create the Cloudflare DNS record:

```text
Type: A
Name: mc
Content: 130.61.33.233
Proxy status: DNS only

Type: SRV
Name: _minecraft._tcp.mc
Priority: 0
Weight: 0
Port: 25677
Target: mc.attentionisallineed.xyz
Proxy status: DNS only
```

Then open Minecraft's TCP port in Oracle Cloud ingress rules:

```text
Source CIDR: 0.0.0.0/0
IP Protocol: TCP
Destination Port Range: 25677
Description: Minecraft Java server
```

Check whether `ufw` is active on the VM:

```bash
sudo ufw status verbose
```

If it says `Status: active`, allow Minecraft:

```bash
sudo ufw allow 25677/tcp
```

Create the VM-only environment file:

```bash
cd /opt/northstar/infra/apps/minecraft
cp .env.example .env
nano .env
```

Set `OPS` to your exact Minecraft Java username, or leave it blank for first boot. Placeholder usernames can stop startup if the server image tries to resolve them. Leave the real `.env` on the VM only; it is ignored by git.

This server currently uses `ONLINE_MODE=FALSE`. Before opening it to players, keep these plugins installed in `/opt/northstar/apps/minecraft/data/plugins`:

- `AuthMe-6.0.0-Paper.jar` for `/register` and `/login`.
- `SimpleWhitelist.jar` for name-based whitelist commands.
- `SkinsRestorer.jar` for skins in offline mode.
- `QuickSortX-1.5.jar` for container sorting.
- `TreeFeller-1.30.1.jar` for safe tree felling.
- `logblock-1.0.5.jar` for block placement/break history and anti-grief inspection.

SimpleWhitelist uses the normal whitelist command name:

```bash
docker exec -i northstar-minecraft rcon-cli "whitelist on"
docker exec -i northstar-minecraft rcon-cli "whitelist add Cruetto"
docker exec -i northstar-minecraft rcon-cli "whitelist list"
```

The compose file sets the public server-list `MOTD` directly as a YAML multiline value. Do not set `SERVER_NAME` in the VM-only `.env`.

The server resource pack is a merged zip served from `/opt/northstar/resourcepacks/northstar-resource-pack.zip` at `https://mc.attentionisallineed.xyz/resourcepacks/northstar-resource-pack.zip`. Its layer order is `Rethoughted GUI` over `Vanilla Experience+` over `spook's tweaks`.

Start the server:

```bash
cd /opt/northstar/infra/apps/minecraft
docker compose up -d
docker compose logs -f minecraft
```

After `.env` exists, the general infra deployment script will also keep this stack running:

```bash
bash /opt/northstar/infra/scripts/deploy-infra.sh
```

Create a manual world backup:

```bash
bash /opt/northstar/infra/scripts/backup-minecraft.sh
```

The script uses `sudo tar` so it can read all server-owned world files. For unattended cron backups, allow the `ubuntu` user to run tar without a password:

```bash
echo 'ubuntu ALL=(root) NOPASSWD: /usr/bin/tar' | sudo tee /etc/sudoers.d/northstar-minecraft-backup
sudo chmod 440 /etc/sudoers.d/northstar-minecraft-backup
sudo visudo -cf /etc/sudoers.d/northstar-minecraft-backup
```

Backups are stored in:

```text
/opt/northstar/backups/minecraft
```

To run backups every 8 hours, install this cron entry with `crontab -e`:

```cron
0 */8 * * * /bin/bash /opt/northstar/infra/scripts/backup-minecraft.sh >> /opt/northstar/backups/minecraft/backup.log 2>&1
```

The backup script keeps 7 days of `minecraft-world-*.tar.gz` archives by default. Override it for one run with:

```bash
RETENTION_DAYS=30 bash /opt/northstar/infra/scripts/backup-minecraft.sh
```

Verify cron is installed:

```bash
crontab -l
```

Verify backup output and disk usage:

```bash
ls -lh /opt/northstar/backups/minecraft
du -sh /opt/northstar/backups/minecraft
du -sh /opt/northstar/apps/minecraft/data
```

If a backup fails partway through, delete the partial archive before trusting the folder contents.

To pause Minecraft for a long time:

```bash
bash /opt/northstar/infra/scripts/backup-minecraft.sh

cd /opt/northstar/infra/apps/minecraft
docker compose down

crontab -e
```

In crontab, comment the Minecraft backup line:

```cron
# 0 */8 * * * /bin/bash /opt/northstar/infra/scripts/backup-minecraft.sh >> /opt/northstar/backups/minecraft/backup.log 2>&1
```

To resume later:

```bash
cd /opt/northstar/infra/apps/minecraft
docker compose up -d
docker compose logs -f minecraft

crontab -e
```

Then uncomment the backup cron line.

Players connect to:

```text
mc.attentionisallineed.xyz
```

Minecraft uses host port `25677/tcp` directly. Do not route it through Caddy. The server currently uses `ONLINE_MODE=FALSE`, protected by AuthMe plus SimpleWhitelist.

## 5. Start Admin Services

```bash
cd /opt/northstar/infra/admin
docker compose up -d
```

File Browser is configured with no internal login and relies on Caddy Basic Auth for the northstar admin domain. Use `vallutto` for the Caddy Basic Auth username in `/opt/northstar/infra/proxy/.env`.

The admin status service reads host CPU, RAM, root disk usage, Docker container stats, Minecraft's normal server-list status, Minecraft backup files, and Minecraft Docker logs. It stores 10 days of VM/container/Minecraft samples in SQLite under `/opt/northstar/admin/status-data`. The portal renders Docker controls for allowlisted containers, a backup summary with a `Backup now` button, expandable live Docker logs, and a narrow Minecraft command console.
Player profiles in SQLite store nickname, UUID when available from logs, first seen, last seen, join count, leave count, and last action.

Check the status service:

```bash
cd /opt/northstar/infra/admin
docker compose ps status
docker compose logs --tail=40 status
```

The Minecraft panel uses Docker logs for its raw log viewer. Commands entered in the panel are sent through `mc-send-to-console` inside the Minecraft container, with `rcon-cli` only as a fallback, never through a shell.
The Minecraft compose file enables `CREATE_CONSOLE_IN_PIPE=TRUE` so that console command path is available after the next intentional Minecraft restart/recreate.

File Browser mounts only the safe admin files folder. The host path is:

```text
/opt/northstar/admin/files
```

Inside File Browser, that folder appears as:

```text
/
```

If drag-and-drop uploads fail, first fix the folder ownership and permissions on the VM:

```bash
sudo mkdir -p /opt/northstar/admin/files
sudo mkdir -p /opt/northstar/admin/filebrowser/database /opt/northstar/admin/filebrowser/config
sudo chown -R ubuntu:ubuntu /opt/northstar/admin/files /opt/northstar/admin/filebrowser
sudo chmod 775 /opt/northstar/admin/files
sudo chmod -R u+rwX,g+rwX /opt/northstar/admin/files
```

After switching from the old whole-VM File Browser setup, recreate the service so it uses the host-owned database/config folders:

```bash
cd /opt/northstar/infra/admin
docker compose stop filebrowser
docker compose rm -f filebrowser
sudo mkdir -p /opt/northstar/admin/filebrowser/database /opt/northstar/admin/filebrowser/config
sudo chown -R ubuntu:ubuntu /opt/northstar/admin/files /opt/northstar/admin/filebrowser
docker compose up -d filebrowser
```

If this VM still has the old Portainer container or volume, remove them after confirming the new Docker panel works:

```bash
cd /opt/northstar/infra/admin
docker rm -f northstar-portainer
docker volume rm admin_portainer_data
```

## 6. Configure Caddy

Generate a Caddy Basic Auth hash on the VM:

```bash
docker run --rm caddy:2 caddy hash-password --plaintext 'your-real-password'
```

Caddy routes are now git-managed in `/opt/northstar/infra/proxy/Caddyfile`. Keep secrets and VM-specific upstreams in the ignored env file:

```bash
cd /opt/northstar/infra/proxy
cp .env.example .env
nano .env
```

Set:

```env
CADDY_EMAIL=your-real-email@example.com
ADMIN_USERNAME=vallutto
ADMIN_PASSWORD_HASH='<hash from caddy hash-password>'
QUIZZY_UPSTREAM=quizzy-web-1:80
```

Keep single quotes around `ADMIN_PASSWORD_HASH` so Compose does not treat the bcrypt `$` characters as environment-variable syntax.

Quizzy owns the `quizzy-web-1` app proxy in the IndividualTeacher repo. Caddy reaches it over the shared external Docker network `northstar_web`.

## 7. Start or Reload Caddy

If Caddy is already running with Docker Compose:

```bash
cd /opt/northstar/infra/proxy
docker compose up -d
docker compose exec caddy caddy reload --config /etc/caddy/Caddyfile
```

If the reload fails, inspect the logs:

```bash
docker compose logs caddy
```

## 8. Cloudflare

Add these DNS records:

```text
Type: A
Name: attentionisallineed.xyz
Content: 130.61.33.233
Proxy status: Proxied

Type: CNAME
Name: www
Content: attentionisallineed.xyz
Proxy status: Proxied

Type: A
Name: northstar
Content: 130.61.33.233
Proxy status: Proxied

Type: A
Name: cv
Content: 130.61.33.233
Proxy status: Proxied

Type: A
Name: mc
Content: 130.61.33.233
Proxy status: DNS only
```

Keep the existing Quizzy record working.

`quizzy`, `cv`, and `northstar` can all be Cloudflare proxied because Caddy serves HTTPS on the VM. If Cloudflare shows a TLS error such as 525 or 526, check Cloudflare SSL/TLS mode and use `Full (strict)` with Caddy's valid certificates, or temporarily switch the record back to `DNS only` while debugging.

Keep `mc` DNS-only because Minecraft uses raw TCP on host port `25677`, not HTTPS through Caddy.

Cloudflare HTTP security features such as Bot Fight Mode, Cloudflare Managed Rules, AI bot blocking, AI Labyrinth, challenge passage, and managed `robots.txt` apply only to proxied HTTP/HTTPS hostnames. They are useful for `attentionisallineed.xyz`, `www`, `quizzy`, `cv`, and `northstar`, but they do not protect Minecraft Java traffic on the DNS-only `mc` record.

If Minecraft is moved to a non-default port, add an SRV record instead of trying to redirect DNS:

```text
Type: SRV
Name: _minecraft._tcp.mc
Priority: 0
Weight: 0
Port: 25677
Target: mc.attentionisallineed.xyz
Proxy status: DNS only
```

For two-factor protection on the admin portal, use Cloudflare Access in front of `northstar.attentionisallineed.xyz` with an allow policy for your email and one-time PIN login. Caddy Basic Auth stays as the VM-side fallback; Cloudflare Access adds the second factor before traffic reaches Caddy.

## 9. Quizzy Database and OAuth Checks

MongoDB for Quizzy:

- Production MongoDB runs inside the IndividualTeacher app Compose stack as `quizzy-mongo-1`.
- Do not create a Caddy route, Cloudflare DNS record, or Oracle public ingress rule for MongoDB.
- Atlas may remain as rollback/migration history only.

Google OAuth for Quizzy:

- Authorized JavaScript origin: `https://quizzy.attentionisallineed.xyz`
- Authorized redirect URI: `https://quizzy.attentionisallineed.xyz/api/auth/google/callback`

Do not store MongoDB URIs or OAuth secrets in this repo.

## 10. Oracle Cost Safety

Recommended guardrails:

- `standard-a1-core-count` quota set to `4`
- `standard-a1-memory-count` quota set to `24`
- `standard-a2-core-count` quota set to `0`
- `standard-a2-memory-count` quota set to `0`
- Budget alert enabled

The current VM uses the Always Free A1 maximum: 4 OCPU and 24 GB RAM.

## 11. Verify

Open:

- `https://quizzy.attentionisallineed.xyz`
- `https://cv.attentionisallineed.xyz`
- `https://northstar.attentionisallineed.xyz`
- `https://northstar.attentionisallineed.xyz/files/`
- `mc.attentionisallineed.xyz` from Minecraft Java Edition

Expected security layers:

- Northstar domain asks for Caddy Basic Auth first.
- Optional Cloudflare Access asks for email OTP before Caddy if configured.
- File Browser opens at `/files/` after Caddy authentication and does not ask for a second login.
- The portal Docker panel shows allowlisted container stats and common controls.
- The portal backup panel shows Minecraft backup count, total size, recent files, dates, per-file MB, and a manual `Backup now` action.
- Minecraft accepts offline-mode clients because `ONLINE_MODE=FALSE`; AuthMe and SimpleWhitelist are the required safety layer.

## 12. CI/CD Setup

The VM-side scripts are:

```text
/opt/northstar/infra/scripts/deploy-cv.sh
/opt/northstar/infra/scripts/deploy-infra.sh
```

Create a dedicated SSH key for GitHub Actions on your local machine:

```bash
ssh-keygen -t ed25519 -C "github-actions-northstar" -f ./northstar_actions -N ""
```

Add the public key to the VM:

```bash
cat ./northstar_actions.pub
```

Copy the printed public key, then on the VM append it to:

```bash
nano /home/ubuntu/.ssh/authorized_keys
```

Paste the public key on a new line, save, then ensure permissions:

```bash
chmod 700 /home/ubuntu/.ssh
chmod 600 /home/ubuntu/.ssh/authorized_keys
```

In GitHub repository settings, add these Actions secrets:

```text
NORTHSTAR_HOST=130.61.33.233
NORTHSTAR_USER=ubuntu
NORTHSTAR_SSH_KEY=<contents of ./northstar_actions private key>
```

Every push to `northstar-vm/northstar_infra` `main` deploys directly:

```text
GitHub Actions -> SSH northstar -> git pull /opt/northstar/infra -> restart infra services
```

CI force-recreates admin, CV, and proxy/Caddy services. Minecraft is left running with `docker compose up -d --no-recreate`; restart it manually from `/opt/northstar/infra/apps/minecraft` when you intentionally want a Minecraft restart.
