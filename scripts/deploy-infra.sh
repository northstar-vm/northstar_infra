#!/usr/bin/env bash
set -euo pipefail

INFRA_DIR="/opt/northstar/infra"

cd "$INFRA_DIR"
git pull --ff-only

docker network inspect northstar_web >/dev/null 2>&1 || docker network create northstar_web

sudo mkdir -p /opt/northstar/admin/files /opt/northstar/backups /opt/northstar/apps
sudo chown -R ubuntu:ubuntu /opt/northstar/admin/files /opt/northstar/backups /opt/northstar/apps
sudo chmod 775 /opt/northstar/admin/files

cd "$INFRA_DIR/admin"
docker compose up -d

if [ -d /opt/northstar/apps/cv/.git ]; then
  cd "$INFRA_DIR/apps/cv"
  docker compose up -d
fi

if [ -f "$INFRA_DIR/apps/minecraft/.env" ]; then
  sudo mkdir -p /opt/northstar/apps/minecraft/data
  sudo chown -R ubuntu:ubuntu /opt/northstar/apps/minecraft

  cd "$INFRA_DIR/apps/minecraft"
  docker compose up -d
fi

cd "$INFRA_DIR/proxy"
docker compose up -d
docker compose exec -T caddy caddy reload --config /etc/caddy/Caddyfile || true

docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
