-- Let XKB handle Super+Space instead of opening Omarchy root menu.
hl.unbind("SUPER + SPACE")

hl.unbind("SUPER + D")
o.bind("SUPER + D", "Apps", "omarchy-menu toggle apps")

hl.unbind("SUPER + ALT + D")
o.bind("SUPER + ALT + D", "Omarchy menu", "omarchy-menu toggle root")
