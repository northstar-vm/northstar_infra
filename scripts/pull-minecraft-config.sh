#!/usr/bin/env bash
# Copy the live versions of every repo-tracked Minecraft config file from the VM
# back into apps/minecraft/server/, so changes made in-game or by hand on the VM
# can be reviewed with `git diff` and committed. Run from a machine with SSH
# access to the VM. On every container start the repo copy overwrites the live
# one, so anything not pulled and committed is lost at the next restart.
#
# Usage: scripts/pull-minecraft-config.sh [ssh-host]   (default: northstar)
set -euo pipefail

HOST="${1:-northstar}"
DATA_DIR="/opt/northstar/apps/minecraft/data"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SERVER_DIR="$REPO_ROOT/apps/minecraft/server"

cd "$SERVER_DIR"
git ls-files -z . | rsync -a --from0 --files-from=- "$HOST:$DATA_DIR/" "$SERVER_DIR/"
git -C "$REPO_ROOT" status --short -- apps/minecraft/server
