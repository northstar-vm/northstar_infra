# Deployment

These steps assume you are SSH'd into the VM as `ubuntu`.

This repo should become the separate private GitHub repo `northstar-infra`. Do not place these files inside `/opt/northstar/apps/quizzy` or the `cruetto/IndividualTeacher` app repo.

## 1. Prepare Folders

```bash
sudo mkdir -p /opt/northstar/proxy
sudo mkdir -p /opt/northstar/admin/portal
sudo mkdir -p /opt/northstar/admin/files
sudo mkdir -p /opt/northstar/backups
sudo chown -R ubuntu:ubuntu /opt/northstar/admin
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
    proxy/
      docker-compose.yml
      Caddyfile
  proxy/
    old proxy location, no longer used after infra proxy is active
  apps/
    quizzy/
    cv/
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

## 4. Start Admin Services

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

## 5. Configure Caddy

Generate a Caddy Basic Auth hash on the VM:

```bash
docker run --rm caddy:2 caddy hash-password --plaintext 'your-real-password'
```

Create or update `/opt/northstar/proxy/Caddyfile` using `proxy/Caddyfile.example` as a template.

Important: merge the admin host into the existing proxy config. Do not delete or rewrite the existing working Quizzy host unless you intentionally need to update that app route.

Replace:

```text
ADMIN_USERNAME
ADMIN_PASSWORD_HASH_FROM_CADDY
```

with the real username and generated hash on the VM only.

The CV route should point to the CV Nginx service:

```caddy
cv.attentionisallineed.xyz {
	encode zstd gzip
	reverse_proxy cv-web:80
}
```

## 6. Start or Reload Caddy

If Caddy is already running with Docker Compose:

```bash
cd /opt/northstar/proxy
docker compose up -d
docker compose exec caddy caddy reload --config /etc/caddy/Caddyfile
```

If the reload fails, inspect the logs:

```bash
docker compose logs caddy
```

## 7. Cloudflare

Add these DNS records:

```text
Type: A
Name: northstar
Content: 130.61.33.233
Proxy status: Proxied

Type: A
Name: cv
Content: 130.61.33.233
Proxy status: Proxied
```

Keep the existing Quizzy record working.

## 8. Atlas and OAuth Checks

MongoDB Atlas:

- Confirm the backend can connect from the VM.
- Keep `130.61.33.233/32` in Atlas network access.
- Remove temporary `0.0.0.0/0` network access.
- Use the dedicated northstar DB user in VM-only app environment files.

Google OAuth for Quizzy:

- Authorized JavaScript origin: `https://quizzy.attentionisallineed.xyz`
- Authorized redirect URI: `https://quizzy.attentionisallineed.xyz/api/auth/google/callback`

Do not store MongoDB URIs or OAuth secrets in this repo.

## 9. Oracle Cost Safety

Recommended guardrails:

- `standard-a1-core-count` quota set to `4`
- `standard-a1-memory-count` quota set to `24`
- `standard-a2-core-count` quota set to `0`
- `standard-a2-memory-count` quota set to `0`
- Budget alert enabled

The current VM uses the Always Free A1 maximum: 4 OCPU and 24 GB RAM.

## 10. Verify

Open:

- `https://quizzy.attentionisallineed.xyz`
- `https://cv.attentionisallineed.xyz`
- `https://northstar.attentionisallineed.xyz`
- `https://northstar.attentionisallineed.xyz/docker/`
- `https://northstar.attentionisallineed.xyz/files/`

Expected security layers:

- Northstar domain asks for Caddy Basic Auth first.
- Portainer asks for its own login at `/docker/`.
- File Browser asks for its own login at `/files/`.
