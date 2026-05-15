#!/usr/bin/env bash
set -euo pipefail

CV_REPO="https://github.com/cruetto/PortfolioWebsite.git"
CV_DIR="/opt/northstar/apps/cv"
INFRA_DIR="/opt/northstar/infra"

sudo mkdir -p /opt/northstar/apps
sudo chown -R ubuntu:ubuntu /opt/northstar/apps

if [ ! -d "$CV_DIR/.git" ]; then
  git clone "$CV_REPO" "$CV_DIR"
else
  cd "$CV_DIR"
  git fetch origin main
  git reset --hard origin/main
fi

cd "$INFRA_DIR"
git pull --ff-only

docker network inspect northstar_web >/dev/null 2>&1 || docker network create northstar_web

cd "$INFRA_DIR/apps/cv"
docker compose up -d

cd "$INFRA_DIR/proxy"
docker compose up -d
docker compose exec -T caddy caddy reload --config /etc/caddy/Caddyfile || true

curl -fsSI https://cv.attentionisallineed.xyz || true
