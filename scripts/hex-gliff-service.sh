#!/usr/bin/env bash
set -euo pipefail

# Keep Hex's inherited lookup path, but intercept its exact Gliff paste only.
export PATH="$HOME/.local/lib/hex-gliff/bin:$PATH"
export HEX_GLIFF_PASTE=1
exec /usr/bin/hex service "$@"
