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

set +e
sudo tar -C "$DATA_DIR" -czf "$BACKUP_FILE" .
TAR_STATUS=$?
set -e

# tar exits 1 for "file changed as we read it", a benign race with the live
# server process (e.g. logs/latest.log) and not a corrupt archive. Only
# exit codes >1 are fatal tar errors.
if [ "$TAR_STATUS" -gt 1 ]; then
  echo "tar failed with exit code $TAR_STATUS, discarding $BACKUP_FILE" >&2
  rm -f "$BACKUP_FILE"
  exit 1
elif [ "$TAR_STATUS" -eq 1 ]; then
  echo "tar reported changed files during backup (exit 1); keeping $BACKUP_FILE" >&2
fi

if docker ps --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; then
  docker exec "$CONTAINER_NAME" rcon-cli save-on >/dev/null
  trap - EXIT
fi

find "$BACKUP_DIR" -type f -name 'minecraft-world-*.tar.gz' -mtime +"$RETENTION_DAYS" -delete

echo "$BACKUP_FILE"
