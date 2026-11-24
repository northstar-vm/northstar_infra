# Force keepInventory on, then re-check every 30s so nothing can flip it back.
gamerule keep_inventory true
schedule function northstar:keepinv 30s
