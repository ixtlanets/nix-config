-- Keep rendering and video decoding on the integrated Intel GPU by default.
hl.env("LIBVA_DRIVER_NAME", "iHD")
hl.env("__GLX_VENDOR_LIBRARY_NAME", "mesa")

-- The advertised 60 Hz timing loses the link during clamshell modesets.
hl.monitor({
  output = "desc:Huawei Technologies Co. Inc. MateView",
  mode = "modeline 619.603 3840 3848 3880 3920 2560 2619 2627 2633 +hsync -vsync",
  position = "0x0",
  scale = 2,
})
