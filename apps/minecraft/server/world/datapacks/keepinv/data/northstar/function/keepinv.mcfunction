# Force keepInventory on in every dimension, then re-check every 30s so nothing can flip it back.
# Paper keeps gamerules per world, so a bare `gamerule` only affects the overworld.
execute in minecraft:overworld run gamerule keep_inventory true
execute in minecraft:the_nether run gamerule keep_inventory true
execute in minecraft:the_end run gamerule keep_inventory true
schedule function northstar:keepinv 30s
