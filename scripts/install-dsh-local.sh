#!/usr/bin/env bash
# Opt-in local workstation service. Preserve the existing DSH home and profile.
set -euo pipefail
umask 077
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

if (( EUID == 0 )); then
  echo 'Run as the intended DSH user, not root.' >&2
  exit 1
fi

for tool in python3 curl systemctl; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    printf 'Missing prerequisite: %s\n' "$tool" >&2
    exit 1
  fi
done
[[ -x /usr/bin/mise ]] || { echo 'Missing prerequisite: /usr/bin/mise' >&2; exit 1; }
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else "Python 3.12+ required")'

# No profile seeding, credential copying, service start, or restart here.
exec python3 "$ROOT/dotfiles/dsh/local/dsh-local" install "$@"
