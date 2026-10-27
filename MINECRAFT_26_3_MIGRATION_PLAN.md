# Minecraft 26.3 Migration & Cleanup Plan

Status: planned, not started. Everything below is to be done together when moving the server from Paper 26.2 to 26.3.

Written 2026-10-27. Server at that time: Paper 26.2 build 134, itzg/minecraft-server:java25.

## Why we are waiting

Paper 26.3 is stable (build 227 on 2026-10-27), but these plugins had no 26.3 build:

| Plugin | Installed | Status |
|---|---|---|
| EtherealPortals | 1.2.0-MC26.2 | No 26.3 build (latest is the 26.2 one) |
| ChestSorter | 2.1.0-MC26.2 | No 26.3 build (latest is the 26.2 one) |
| BlockShips | 0.0.17 | Latest, tagged 26.1.2 / 26.2 only |
| ProtocolLib | dev build | Last release 5.4.0 (Aug 2025); 26.3 support unconfirmed. May be unused, see below |
| SkinsRestorer | Oct 17 jar | 26.3 builds found were Fabric/NeoForge only; confirm the Paper jar |
| AuthMe | 6.0.0 | 6.0.1 available; 26.3 support unconfirmed |
| TreeFeller, CompassCoords, SimpleWhitelist | | No 26.3 info; probably fine |
| CrazyEnchantments | 2.8.1 | 26.3 builds exist but are betas |
| LogBlock | 1.0.6 | Already supports 26.3 |
| ArmorStandEditor | 26.1.2-51 | 2.14.0 is Fabric-only, not an upgrade for Paper. Keep current jar |

Movecraft is NOT used (jar is `.disabled`); BlockShips is the active ship plugin.

## Gate: start the migration when

- EtherealPortals, ChestSorter and BlockShips have 26.3-compatible builds (check Modrinth / project pages).
- ProtocolLib decision made (see step 3).
- A quiet time with nobody online (`docker exec northstar-minecraft rcon-cli list`).

## Steps

### 1. Repo docs and compose (no server impact)

- Replace the plugin comment in `apps/minecraft/docker-compose.yml` with the real list (drop Movecraft, add BlockShips and the others).
- Fix plugin lists in `README.md`, `DEPLOYMENT.md`, `NORTHSTAR_HANDOFF.md`:
  - Remove QuickSortX (replaced by ChestSorter) and `logblock-1.0.5` (now 1.0.6).
  - Add ArmorStandEditor, BlockShips, ChestSorter, CompassCoords, CrazyEnchantments, EtherealPortals, ProtocolLib (if kept).
  - Dungeons and Taverns is v5.3.0, not v5.2.0.
- Set the Minecraft version explicitly (compose default and `.env.example`) instead of `LATEST`, so a container recreate never upgrades by accident. Use `26.3` at migration time.

### 2. Backup

- Run `scripts/backup-minecraft.sh` and confirm the archive exists before touching anything.

### 3. Verify ProtocolLib

- Nothing declared a dependency on it in plugin.yml (check was not conclusive). Find out which plugin, if any, needs it (try BlockShips, CrazyEnchantments, SkinsRestorer docs/logs).
- If unused: disable it (`.disabled`) for a trial run, then delete. If needed: use a build that supports 26.3.

### 4. Server cleanup (`/opt/northstar/apps/minecraft/data/plugins`)

Delete, after the backup:

- `Movecraft-26.2.jar.disabled`, `QuickSortX-1.5.jar.disabled`, `CoreProtect-CE-23.2.jar.disabled`, `logblock-1.0.5.jar.disabled`, `EtherealPortals.jar.disabled`
- Folders `Movecraft/` and `QuickSortX/`
- `~/plugin-updates` on the VM, after checking nothing in it is unique (it holds already-installed jars, the Movecraft dev jar, datapack zips, `blocks.yml`, `hideportalnames`)

Keep the `LogBlock/` folder (71M of block history).

### 5. Test on a copy first

- Run a throwaway 26.3 container on a different port against a copy of the world and read the plugin load errors.
- Check portals, chest sorting, ships, enchantments, login/skins before touching the live server.

### 6. Upgrade the live server

- Install the updated plugin jars (26.3 builds of EtherealPortals, ChestSorter, BlockShips; AuthMe 6.0.1; others as needed).
- Fix ChestSorter config: `ITEM_BOOK_PAGE_TURN` is an invalid sound name (about 800 warnings in the log). Use the current sound name.
- Pin `MINECRAFT_VERSION=26.3`, recreate the container, and watch the startup log for errors.
- Smoke test in game: login, portals, ships, chest sorting, tree felling, enchantments, resource pack.

### 7. Rollback

- Restore the backup from step 2 and set `MINECRAFT_VERSION=26.2` back. Do not start 26.2 on a world that has been opened by 26.3 without the backup.

## Known harmless warnings (no action)

- AuthMe: GeoIP database missing, PacketEvents/protectInventory disabled.
- Offline-mode warning (intentional, AuthMe handles auth).
- SimpleWhitelist does not specify an api-version.
- joml `sun.misc.Unsafe` warning.
