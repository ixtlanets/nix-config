#!/usr/bin/env python3
"""Opt-in Hex 3.3.0 paste adapter for /usr/bin/gliff omarchy-vm.

Expose this script as /home/nik/.local/lib/hex-gliff/bin/wtype, prepend that
private directory to the Hex service's PATH, and set HEX_GLIFF_PASTE=1 there.
Remove that PATH entry or unset the flag to disable. No clipboard access,
logging, network calls, or changes to the system wtype are needed.
"""

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time


REAL_WTYPE = "/usr/bin/wtype"
GLIFF_EXE = "/usr/bin/gliff"
GLIFF_ENDPOINT = b"omarchy-vm"
GLIFF_TITLE = "omarchy-vm — Gliff"
FEATURE = "HEX_GLIFF_PASTE"
HEX_ARGS = [part for code in range(0x2460, 0x248E) for part in ("-p", f"U{code:04X}")]
HEX_ARGS += ["-M", "ctrl", "-k", "v", "-m", "ctrl", "-p", "VoidSymbol"]

# Accepted native fix: explicit Control_L events as well as the modifier mask.
# The compositor, not this helper, owns the release timer.
GLIFF_NATIVE_PASTE = (
    'hl.dispatch(hl.dsp.send_key_state({mods="",key="Control_L",state="down"})); '
    'hl.dispatch(hl.dsp.send_key_state({mods="CTRL",key="V",state="down"})); '
    'hl.timer(function() '
    'hl.dispatch(hl.dsp.send_key_state({mods="CTRL",key="V",state="up"})); '
    'hl.dispatch(hl.dsp.send_key_state({mods="",key="Control_L",state="up"})) '
    'end,{timeout=50,type="oneshot"})'
)


def focused_gliff():
    """Return a verified focus snapshot, or decline interception on any uncertainty."""
    try:
        result = subprocess.run(
            ["hyprctl", "-j", "activewindow"], capture_output=True,
            text=True, timeout=0.5, check=True,
        )
        window = json.loads(result.stdout)
        if not isinstance(window, dict):
            return None
        cls, title = window.get("class"), window.get("title")
        pid, address = window.get("pid"), window.get("address")
        if not isinstance(cls, str) or cls.lower() != "gliff" or title != GLIFF_TITLE:
            return None
        if type(pid) is not int or pid <= 0:
            return None
        if not isinstance(address, str) or not re.fullmatch(r"0x[0-9a-fA-F]+", address):
            return None
        if int(address, 16) == 0:
            return None
        proc = Path("/proc") / str(pid)
        # /proc/exe identifies the actual binary, not a spoofable argv[0].
        if os.readlink(proc / "exe") != GLIFF_EXE:
            return None
        command = (proc / "cmdline").read_bytes().split(b"\0")
        if GLIFF_ENDPOINT not in command[1:]:
            return None
        return window
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def native_paste(window):
    """Recheck focus atomically with keydown; never retry an uncertain paste."""
    # Only the validated hexadecimal address, integer PID and fixed title enter
    # Lua. A focus race must fail before any key state is injected.
    command = (
        'local window = hl.get_active_window(); '
        f'assert(window and window.address == "{window["address"]}" '
        f'and window.pid == {window["pid"]} '
        f'and window.title == {json.dumps(GLIFF_TITLE, ensure_ascii=False)} '
        'and window.class:lower() == "gliff", "Hex Gliff focus changed"); '
        + GLIFF_NATIVE_PASTE
    )
    try:
        result = subprocess.run(
            ["hyprctl", "eval", command], capture_output=True,
            text=True, timeout=1.0, check=True,
        )
        # Some hyprctl errors can be returned as text with a zero process status.
        if result.stdout.strip() != "ok":
            raise RuntimeError("Native Gliff paste was not acknowledged")
    finally:
        # Hex must not finish its paste before the compositor's 50 ms keyup.
        # Also allow a possibly submitted timer to run after an uncertain error.
        time.sleep(0.1)


def main():
    original = sys.argv[1:]
    window = None
    if os.environ.get(FEATURE) == "1" and original == HEX_ARGS:
        window = focused_gliff()
    if window is None:
        os.execv(REAL_WTYPE, [REAL_WTYPE, *original])
        return 0  # Only reached by mocks; successful exec replaces this process.
    try:
        native_paste(window)
    except (OSError, RuntimeError, subprocess.SubprocessError):
        # Injection may already have happened: falling back could paste twice.
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
