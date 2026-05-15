# Deployment

These steps assume you are SSH'd into the VM as `ubuntu`.

This repo should become the separate private GitHub repo `northstar-infra`. Do not place these files inside `/opt/northstar/apps/quizzy` or the `cruetto/IndividualTeacher` app repo.

## 1. Prepare Folders

```bash
sudo mkdir -p /opt/northstar/proxy
sudo mkdir -p /opt/northstar/admin/portal
sudo mkdir -p /opt/northstar/admin/files
sudo chown -R ubuntu:ubuntu /opt/northstar/admin
```

Copy this repo's files to `/opt/northstar` without mixing them into `/opt/northstar/apps/quizzy`.

Expected layout:

```text
/opt/northstar/
  admin/
    docker-compose.yml
    portal/
      index.html
    files/
  proxy/
    docker-compose.yml
    Caddyfile
  apps/
    quizzy/
```

## 2. Create the Admin Docker Network

The proxy and admin services communicate on a shared Docker network:

```bash
docker network create northstar_web
```

If it already exists, Docker will say so; that is fine.

## 3. Start Admin Services

```bash
cd /opt/northstar/admin
docker compose up -d
```

Portainer will initialize on first visit and ask you to create its admin user.

File Browser will create its database on first run. Change its default credentials immediately inside the File Browser UI.

## 4. Configure Caddy

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

## 5. Start or Reload Caddy

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

## 6. Cloudflare

Add this DNS record:

```text
Type: A
Name: northstar
Content: 130.61.33.233
Proxy status: Proxied
```

Keep the existing Quizzy record working.

## 7. Atlas and OAuth Checks

MongoDB Atlas:

- Confirm the backend can connect from the VM.
- Keep `130.61.33.233/32` in Atlas network access.
- Remove temporary `0.0.0.0/0` network access.
- Use the dedicated northstar DB user in VM-only app environment files.

Google OAuth for Quizzy:

- Authorized JavaScript origin: `https://quizzy.attentionisallineed.xyz`
- Authorized redirect URI: `https://quizzy.attentionisallineed.xyz/api/auth/google/callback`

Do not store MongoDB URIs or OAuth secrets in this repo.

## 8. Oracle Cost Safety

Recommended guardrails:

- `standard-a1-core-count` quota set to `4`
- `standard-a1-memory-count` quota set to `24`
- `standard-a2-core-count` quota set to `0`
- `standard-a2-memory-count` quota set to `0`
- Budget alert enabled

The current VM uses the Always Free A1 maximum: 4 OCPU and 24 GB RAM.

## 9. Verify

Open:

- `https://quizzy.attentionisallineed.xyz`
- `https://northstar.attentionisallineed.xyz`
- `https://northstar.attentionisallineed.xyz/docker/`
- `https://northstar.attentionisallineed.xyz/files/`

Expected security layers:

- Northstar domain asks for Caddy Basic Auth first.
- Portainer asks for its own login at `/docker/`.
- File Browser asks for its own login at `/files/`.
