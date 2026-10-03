#!/usr/bin/env bash
# Deliberately not using 'set -e': a single transient failure (RCON hiccup,
# tar warning) must not silently abort the whole run. Every failure path
# below is handled and logged explicitly instead.
set -uo pipefail

CONTAINER_NAME="northstar-minecraft"
DATA_DIR="/opt/northstar/apps/minecraft/data"
BACKUP_DIR="/opt/northstar/backups/minecraft"
# Count-based retention: keep the most recent MAX_BACKUPS archives. Eviction
# only ever happens right after this run successfully adds a new one, and
# only removes the single oldest archive(s) needed to get back under the
# cap. 21 is ~7 days at the default every-8-hours cron cadence. This means a
# long outage (cron failing silently for weeks) can't wipe the whole backlog
# in one shot once backups resume -- it only ever evicts one old file per
# new one added.
MAX_BACKUPS="${MAX_BACKUPS:-21}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_FILE="$BACKUP_DIR/minecraft-world-$TIMESTAMP.tar.gz"

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }

log "Starting backup -> $BACKUP_FILE"

if [ ! -d "$DATA_DIR" ]; then
  log "ERROR: Minecraft data directory not found: $DATA_DIR"
  exit 1
fi

mkdir -p "$BACKUP_DIR"

CONTAINER_RUNNING=0
if docker ps --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; then
  CONTAINER_RUNNING=1
  # Set before attempting save-off so save-on always gets attempted on exit,
  # even if save-off itself fails partway through.
  trap 'docker exec "$CONTAINER_NAME" rcon-cli save-on >/dev/null 2>&1 || true' EXIT
  if ! docker exec "$CONTAINER_NAME" rcon-cli save-off >/dev/null 2>&1; then
    log "WARNING: rcon save-off failed, continuing with a best-effort backup"
  elif ! docker exec "$CONTAINER_NAME" rcon-cli save-all flush >/dev/null 2>&1; then
    log "WARNING: rcon save-all flush failed, continuing with a best-effort backup"
  fi
fi

sudo tar -C "$DATA_DIR" -czf "$BACKUP_FILE" .
TAR_STATUS=$?

if [ "$CONTAINER_RUNNING" -eq 1 ]; then
  docker exec "$CONTAINER_NAME" rcon-cli save-on >/dev/null 2>&1 || true
  trap - EXIT
fi

# tar exits 1 for "file changed as we read it", a benign race with the live
# server process (e.g. logs/latest.log) and not a corrupt archive. Only
# exit codes >1 are fatal tar errors.
if [ "$TAR_STATUS" -gt 1 ]; then
  log "ERROR: tar failed with exit code $TAR_STATUS, discarding $BACKUP_FILE"
  rm -f "$BACKUP_FILE"
  exit 1
elif [ "$TAR_STATUS" -eq 1 ]; then
  log "tar reported changed files during backup (exit 1); keeping $BACKUP_FILE"
else
  log "Backup created: $BACKUP_FILE ($(du -h "$BACKUP_FILE" | cut -f1))"
fi

mapfile -t SORTED < <(find "$BACKUP_DIR" -maxdepth 1 -type f -name 'minecraft-world-*.tar.gz' -printf '%T@ %p\n' | sort -n | cut -d' ' -f2-)
DELETED=0
while [ "${#SORTED[@]}" -gt "$MAX_BACKUPS" ]; do
  rm -f "${SORTED[0]}"
  SORTED=("${SORTED[@]:1}")
  DELETED=$((DELETED + 1))
done
if [ "$DELETED" -gt 0 ]; then
  log "Retention: deleted $DELETED oldest backup(s), keeping the most recent $MAX_BACKUPS"
fi

echo "$BACKUP_FILE"
