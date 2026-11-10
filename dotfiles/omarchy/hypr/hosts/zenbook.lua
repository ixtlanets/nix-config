-- Keep rendering and video decoding on the integrated Intel GPU by default.
hl.env("LIBVA_DRIVER_NAME", "iHD")
hl.env("__GLX_VENDOR_LIBRARY_NAME", "mesa")

-- Send Right Alt to Hex's registered push-to-talk shortcut instead of Voxtype.
-- Keep push-to-talk local even when Gliff inhibits compositor shortcuts.
-- Transparent keeps other key releases from shadowing the held Lua global bind.
hl.unbind("ALT + Alt_R")
o.bind("ALT + Alt_R", "Hex dictation (hold)", hl.dsp.global("anomaly.hex:dictation-F8"), { ignore_mods = true, transparent = true, dont_inhibit = true })

-- The advertised 60 Hz timing loses the link during clamshell modesets.
hl.monitor({
  output = "desc:Huawei Technologies Co. Inc. MateView",
  mode = "modeline 619.603 3840 3848 3880 3920 2560 2619 2627 2633 +hsync -vsync",
  position = "0x0",
  scale = 2,
})
