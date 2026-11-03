-- Give this host's function keys to Hex after Omarchy's default bindings load.
hl.unbind("F8")
hl.unbind("F9")
hl.bind("F8", hl.dsp.global("anomaly.hex:dictation-F8"))
hl.bind("F9", hl.dsp.global("anomaly.hex:capture-F9"))
