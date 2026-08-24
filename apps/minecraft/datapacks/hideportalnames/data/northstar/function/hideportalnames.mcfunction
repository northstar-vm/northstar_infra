# EtherealPortals spawns its portal name labels as text_display entities with
# see_through hardcoded true, which renders them through blocks. There's no
# plugin config for this, so we periodically force it back off here.
execute as @e[type=minecraft:text_display] run data merge entity @s {see_through:0b}
schedule function northstar:hideportalnames 10s
