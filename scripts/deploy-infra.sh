#!/usr/bin/env bash
set -euo pipefail

LOCK_FILE="/opt/northstar/deploy-infra.lock"
INFRA_DIR="/opt/northstar/infra"

exec 9>"$LOCK_FILE"
if ! flock -w 600 9; then
  echo "Another deploy-infra.sh run is still active after waiting 10 minutes." >&2
  exit 1
fi

cd "$INFRA_DIR"
git pull --ff-only

docker network inspect northstar_web >/dev/null 2>&1 || docker network create northstar_web

NORTHSTAR_FILE_UID="$(id -u ubuntu)"
NORTHSTAR_FILE_GID="$(id -g ubuntu)"
export NORTHSTAR_FILE_UID NORTHSTAR_FILE_GID
MINECRAFT_UID="${MINECRAFT_UID:-1000}"
MINECRAFT_GID="${MINECRAFT_GID:-1000}"

sudo mkdir -p /opt/northstar/admin/files /opt/northstar/admin/filebrowser/database /opt/northstar/admin/filebrowser/config /opt/northstar/admin/status-data /opt/northstar/backups/minecraft /opt/northstar/apps /opt/northstar/resourcepacks
sudo chown -R "$NORTHSTAR_FILE_UID:$NORTHSTAR_FILE_GID" /opt/northstar/admin/files /opt/northstar/admin/filebrowser
sudo chown -R ubuntu:ubuntu /opt/northstar/backups /opt/northstar/apps /opt/northstar/resourcepacks
sudo chown -R root:root /opt/northstar/admin/status-data
sudo chmod 775 /opt/northstar/admin/files
sudo chmod -R u+rwX,g+rwX /opt/northstar/admin/files

cd "$INFRA_DIR/admin"
docker compose up -d --force-recreate

if [ -d /opt/northstar/apps/cv/.git ]; then
  cd "$INFRA_DIR/apps/cv"
  docker compose up -d --force-recreate
fi

if [ -f "$INFRA_DIR/apps/minecraft/.env" ]; then
  MINECRAFT_DATA="/opt/northstar/apps/minecraft/data"

  sudo mkdir -p "$MINECRAFT_DATA"
  sudo chown -R "$MINECRAFT_UID:$MINECRAFT_GID" "$MINECRAFT_DATA"
  sudo chmod -R u+rwX,g+rwX "$MINECRAFT_DATA"

  # Repo config in apps/minecraft/server is applied by the container on its next
  # start; here we only warn if manually installed binaries drift from the manifest.
  if ! (cd "$MINECRAFT_DATA" && grep -v '^#' "$INFRA_DIR/apps/minecraft/binaries.sha256" | sudo sha256sum -c --quiet - ); then
    echo "WARNING: Minecraft binaries differ from apps/minecraft/binaries.sha256" >&2
  fi
  untracked_bins="$(cd "$MINECRAFT_DATA" && comm -13 \
    <(grep -v '^#' "$INFRA_DIR/apps/minecraft/binaries.sha256" | sed 's/^[0-9a-f]*  //' | sort) \
    <(sudo find plugins world/datapacks -maxdepth 1 -type f \( -name '*.jar' -o -name '*.zip' \) | sort))"
  if [ -n "$untracked_bins" ]; then
    echo "WARNING: Minecraft binaries not listed in apps/minecraft/binaries.sha256:" >&2
    echo "$untracked_bins" >&2
  fi

  cd "$INFRA_DIR/apps/minecraft"
  docker compose up -d --no-recreate
fi

cd "$INFRA_DIR/proxy"
if [ ! -f .env ]; then
  echo "Missing $INFRA_DIR/proxy/.env. Copy proxy/.env.example to proxy/.env on the VM and fill in real values." >&2
  exit 1
fi
docker compose up -d --force-recreate
docker compose exec -T caddy caddy reload --config /etc/caddy/Caddyfile || true

docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
