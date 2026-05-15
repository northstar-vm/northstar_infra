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
- Existing Caddy proxy folder: `/opt/northstar/proxy`
- Existing Quizzy app: `/opt/northstar/apps/quizzy`
- Quizzy domain: `https://quizzy.attentionisallineed.xyz`
- Admin portal domain: `https://northstar.attentionisallineed.xyz`

## Existing App

Quizzy / IndividualTeacher is already deployed from the app repo:

```text
cruetto/IndividualTeacher
```

Current app details:

- Compose services: `backend`, `frontend`, `web`
- Backend runs in Docker on port `5000`
- Frontend runs in Docker/nginx on port `80`
- App `web`/nginx exposes server port `8080`
- MongoDB is MongoDB Atlas, not hosted on this VM
- Caddy already proxies `quizzy.attentionisallineed.xyz` to the working app web service

Keep that working Caddy route intact when adding the northstar admin route.

## What This Adds

- `https://northstar.attentionisallineed.xyz/` - static admin portal page
- `https://northstar.attentionisallineed.xyz/docker/` - Portainer CE
- `https://northstar.attentionisallineed.xyz/files/` - File Browser

The admin domain is protected with Caddy Basic Auth. Portainer and File Browser keep their own application logins as a second layer.

## File Browser Scope

File Browser is configured to expose the VM filesystem at:

```text
/
```

Inside File Browser this appears under `/srv`, so the main server folder is:

```text
/srv/opt/northstar
```

This gives browser-based write access to the server filesystem. Keep the northstar domain protected with Caddy Basic Auth, keep File Browser's own login enabled, and avoid editing system paths such as `/srv/etc`, `/srv/usr`, `/srv/boot`, `/srv/var/lib/docker`, and Docker volume internals unless you intentionally need to.

Good places for manual files:

```text
/srv/opt/northstar/admin/files
/srv/opt/northstar/backups
/srv/home/ubuntu
```

## Secrets

Do not commit real passwords, Caddy hashes, Portainer data, File Browser databases, or runtime volumes.

Also do not commit API keys, private SSH keys, MongoDB connection strings, Google OAuth secrets, or real VM-only config.

Generate a Caddy Basic Auth hash on the VM:

```bash
docker run --rm caddy:2 caddy hash-password --plaintext 'replace-this-password'
```

Then put the resulting hash only in the real VM Caddyfile.

## Cloudflare

Cloudflare manages DNS for `attentionisallineed.xyz`. Hostinger is only the registrar, with nameservers set to:

- `kay.ns.cloudflare.com`
- `lex.ns.cloudflare.com`

Create this DNS record:

| Type | Name | Content | Proxy |
| --- | --- | --- | --- |
| `A` | `northstar` | `130.61.33.233` | Enabled |

Keep the existing Quizzy DNS record as-is.

## External Services

MongoDB Atlas:

- Restrict Atlas IP access to `130.61.33.233/32` after confirming the VM can connect.
- Remove temporary `0.0.0.0/0` access once the VM-specific rule works.
- Use a dedicated DB user for the northstar deployment.

Google OAuth for Quizzy:

- Authorized JavaScript origin: `https://quizzy.attentionisallineed.xyz`
- Authorized redirect URI: `https://quizzy.attentionisallineed.xyz/api/auth/google/callback`

Oracle cost guardrails:

- A1 quota: `standard-a1-core-count` set to `4`
- A1 memory quota: `standard-a1-memory-count` set to `24`
- A2 quotas set to `0`
- Budget alert enabled
