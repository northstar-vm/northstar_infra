#!/usr/bin/env bash
set -euo pipefail

CONTAINER_NAME="northstar-minecraft"
DATA_DIR="/opt/northstar/apps/minecraft/data"
BACKUP_DIR="/opt/northstar/backups/minecraft"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_FILE="$BACKUP_DIR/minecraft-world-$TIMESTAMP.tar.gz"

if [ ! -d "$DATA_DIR" ]; then
  echo "Minecraft data directory not found: $DATA_DIR" >&2
  exit 1
fi

mkdir -p "$BACKUP_DIR"

if docker ps --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; then
  docker exec "$CONTAINER_NAME" rcon-cli save-off >/dev/null
  docker exec "$CONTAINER_NAME" rcon-cli save-all flush >/dev/null
  trap 'docker exec "$CONTAINER_NAME" rcon-cli save-on >/dev/null || true' EXIT
fi

if ! sudo tar -C "$DATA_DIR" -czf "$BACKUP_FILE" .; then
  rm -f "$BACKUP_FILE"
  exit 1
fi

if docker ps --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; then
  docker exec "$CONTAINER_NAME" rcon-cli save-on >/dev/null
  trap - EXIT
fi

find "$BACKUP_DIR" -type f -name 'minecraft-world-*.tar.gz' -mtime +"$RETENTION_DAYS" -delete

echo "$BACKUP_FILE"
