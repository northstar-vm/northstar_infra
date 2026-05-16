# Deployment

These steps assume you are SSH'd into the VM as `ubuntu`.

This repo should become the separate private GitHub repo `northstar-infra`. Do not place these files inside `/opt/northstar/apps/quizzy` or the `cruetto/IndividualTeacher` app repo.

## 1. Prepare Folders

```bash
sudo mkdir -p /opt/northstar/infra
sudo mkdir -p /opt/northstar/admin/portal
sudo mkdir -p /opt/northstar/admin/files
sudo mkdir -p /opt/northstar/apps/minecraft/data
sudo mkdir -p /opt/northstar/backups
sudo chown -R ubuntu:ubuntu /opt/northstar/admin
sudo chown -R ubuntu:ubuntu /opt/northstar/apps/minecraft
sudo chown -R ubuntu:ubuntu /opt/northstar/backups
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
```

Then open Minecraft's TCP port in Oracle Cloud ingress rules:

```text
Source CIDR: 0.0.0.0/0
IP Protocol: TCP
Destination Port Range: 25565
Description: Minecraft Java server
```

Check whether `ufw` is active on the VM:

```bash
sudo ufw status verbose
```

If it says `Status: active`, allow Minecraft:

```bash
sudo ufw allow 25565/tcp
```

Create the VM-only environment file:

```bash
cd /opt/northstar/infra/apps/minecraft
cp .env.example .env
nano .env
```

Set `OPS` to your exact licensed Minecraft Java username, or leave it blank for first boot. Placeholder usernames will stop startup because the server image tries to resolve them. Leave the real `.env` on the VM only; it is ignored by git.

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

Players connect to:

```text
mc.attentionisallineed.xyz
```

Minecraft uses port `25565/tcp` directly. Do not route it through Caddy, and keep `ONLINE_MODE=TRUE` so only authenticated paid Java Edition accounts can join.

## 5. Start Admin Services

```bash
cd /opt/northstar/infra/admin
docker compose up -d
```

Portainer will initialize on first visit and ask you to create its admin user.

File Browser will create its database on first run. Change its default credentials immediately inside the File Browser UI.

File Browser mounts the VM root filesystem at `/srv` in the browser. This is intentionally powerful: use it for operational edits and file management, but avoid changing system directories unless you know why.

Useful browser paths:

```text
/srv/opt/northstar
/srv/opt/northstar/admin/files
/srv/opt/northstar/backups
/srv/home/ubuntu
```

If File Browser rejects credentials, read the generated password from logs:

```bash
docker compose logs filebrowser | grep -i password
```

If needed, reset the File Browser database volume and recreate the service:

```bash
docker rm -f northstar-filebrowser
docker volume ls | grep filebrowser
docker volume rm THE_FILEBROWSER_VOLUME_NAME
docker compose up -d filebrowser
docker compose logs filebrowser | grep -i password
```

## 6. Configure Caddy

Generate a Caddy Basic Auth hash on the VM:

```bash
docker run --rm caddy:2 caddy hash-password --plaintext 'your-real-password'
```

Create or update `/opt/northstar/infra/proxy/Caddyfile` using `proxy/Caddyfile.example` as a template.

Important: merge the admin host into the existing proxy config. Do not delete or rewrite the existing working Quizzy host unless you intentionally need to update that app route.

Replace:

```text
ADMIN_USERNAME
ADMIN_PASSWORD_HASH_FROM_CADDY
```

with the real username and generated hash on the VM only.

The CV route should point to the CV Nginx service:

```caddy
attentionisallineed.xyz {
	redir https://cv.attentionisallineed.xyz{uri}
}

www.attentionisallineed.xyz {
	redir https://cv.attentionisallineed.xyz{uri}
}

cv.attentionisallineed.xyz {
	encode zstd gzip
	reverse_proxy cv-web:80
}
```

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

Keep `mc` DNS-only because Minecraft uses raw TCP on `25565`, not HTTPS through Caddy.

## 9. Atlas and OAuth Checks

MongoDB Atlas:

- Confirm the backend can connect from the VM.
- Keep `130.61.33.233/32` in Atlas network access.
- Remove temporary `0.0.0.0/0` network access.
- Use the dedicated northstar DB user in VM-only app environment files.

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
- `https://northstar.attentionisallineed.xyz/docker/`
- `https://northstar.attentionisallineed.xyz/files/`
- `mc.attentionisallineed.xyz` from Minecraft Java Edition

Expected security layers:

- Northstar domain asks for Caddy Basic Auth first.
- Portainer asks for its own login at `/docker/`.
- File Browser asks for its own login at `/files/`.
- Minecraft requires a licensed Java Edition account because `ONLINE_MODE=TRUE`.

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

For CV CI/CD:

```text
Copy github-actions-templates/deploy-cv.yml
to cruetto/PortfolioWebsite/.github/workflows/deploy-cv.yml
```

Then every push to `PortfolioWebsite/main` deploys:

```text
GitHub Actions -> SSH northstar -> git pull /opt/northstar/apps/cv -> restart CV Nginx
```

For infra CI/CD:

```text
Copy github-actions-templates/deploy-infra.yml
to this repo as .github/workflows/deploy-infra.yml
```

Then every push to `northstar_infra/main` deploys:

```text
GitHub Actions -> SSH northstar -> git pull /opt/northstar/infra -> restart infra services
```
