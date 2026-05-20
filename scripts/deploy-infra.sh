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
  PAPER_GLOBAL_CONFIG="/opt/northstar/apps/minecraft/data/config/paper-global.yml"

  sudo mkdir -p /opt/northstar/apps/minecraft/data
  sudo chown -R "$MINECRAFT_UID:$MINECRAFT_GID" /opt/northstar/apps/minecraft/data
  sudo chmod -R u+rwX,g+rwX /opt/northstar/apps/minecraft/data
  sudo mkdir -p "$(dirname "$PAPER_GLOBAL_CONFIG")"
  if [ ! -f "$PAPER_GLOBAL_CONFIG" ]; then
    printf "spark:\n  enable-immediately: false\n  enabled: false\n" | sudo tee "$PAPER_GLOBAL_CONFIG" >/dev/null
  elif sudo grep -q '^spark:' "$PAPER_GLOBAL_CONFIG"; then
    sudo sed -i '/^spark:/,/^[^[:space:]]/ s/^  enable-immediately: .*/  enable-immediately: false/' "$PAPER_GLOBAL_CONFIG"
    sudo sed -i '/^spark:/,/^[^[:space:]]/ s/^  enabled: .*/  enabled: false/' "$PAPER_GLOBAL_CONFIG"
  else
    printf "\nspark:\n  enable-immediately: false\n  enabled: false\n" | sudo tee -a "$PAPER_GLOBAL_CONFIG" >/dev/null
  fi
  sudo chown "$MINECRAFT_UID:$MINECRAFT_GID" "$PAPER_GLOBAL_CONFIG"
  sudo chmod 664 "$PAPER_GLOBAL_CONFIG"

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
