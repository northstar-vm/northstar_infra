#!/usr/bin/env bash
set -euo pipefail

INFRA_DIR="/opt/northstar/infra"

cd "$INFRA_DIR"
git pull --ff-only

docker network inspect northstar_web >/dev/null 2>&1 || docker network create northstar_web

NORTHSTAR_FILE_UID="$(id -u ubuntu)"
NORTHSTAR_FILE_GID="$(id -g ubuntu)"
export NORTHSTAR_FILE_UID NORTHSTAR_FILE_GID

sudo mkdir -p /opt/northstar/admin/files /opt/northstar/admin/filebrowser/database /opt/northstar/admin/filebrowser/config /opt/northstar/admin/status-data /opt/northstar/backups /opt/northstar/apps
sudo chown -R "$NORTHSTAR_FILE_UID:$NORTHSTAR_FILE_GID" /opt/northstar/admin/files /opt/northstar/admin/filebrowser
sudo chown -R ubuntu:ubuntu /opt/northstar/backups /opt/northstar/apps
sudo chown -R root:root /opt/northstar/admin/status-data
sudo chmod 775 /opt/northstar/admin/files
sudo chmod -R u+rwX,g+rwX /opt/northstar/admin/files

cd "$INFRA_DIR/admin"
docker compose up -d

if [ -d /opt/northstar/apps/cv/.git ]; then
  cd "$INFRA_DIR/apps/cv"
  docker compose up -d
fi

if [ -f "$INFRA_DIR/apps/minecraft/.env" ]; then
  sudo mkdir -p /opt/northstar/apps/minecraft/data
  sudo chown -R ubuntu:ubuntu /opt/northstar/apps/minecraft
  sudo chmod -R u+rwX,g+rwX /opt/northstar/apps/minecraft/data

  cd "$INFRA_DIR/apps/minecraft"
  docker compose up -d
fi

cd "$INFRA_DIR/proxy"
if [ ! -f .env ]; then
  echo "Missing $INFRA_DIR/proxy/.env. Copy proxy/.env.example to proxy/.env on the VM and fill in real values." >&2
  exit 1
fi
docker compose up -d
docker compose exec -T caddy caddy reload --config /etc/caddy/Caddyfile || true

docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
