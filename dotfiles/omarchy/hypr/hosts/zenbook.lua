-- Keep rendering and video decoding on the integrated Intel GPU by default.
hl.env("LIBVA_DRIVER_NAME", "iHD")
hl.env("__GLX_VENDOR_LIBRARY_NAME", "mesa")
