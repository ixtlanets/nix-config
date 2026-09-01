-- Let XKB handle Super+Space instead of opening Omarchy root menu.
hl.unbind("SUPER + SPACE")

hl.unbind("SUPER + D")
o.bind("SUPER + D", "Apps", "omarchy-menu toggle apps")

hl.unbind("SUPER + ALT + D")
o.bind("SUPER + ALT + D", "Omarchy menu", "omarchy-menu toggle root")

hl.unbind("PRINT")
hl.unbind("SUPER + SHIFT + S")
o.bind("SUPER + SHIFT + S", "Screenshot", "omarchy-capture-screenshot")

o.bind("ALT + SPACE", "Toggle keyboard backlight", "kbd-backlight toggle", { locked = true })

o.bind("SUPER + SHIFT + J", "Next window in group", hl.dsp.group.next())
o.bind("SUPER + SHIFT + K", "Previous window in group", hl.dsp.group.prev())
