#!/usr/bin/env bash
# Opt-in Arch/Omarchy user-service install; never copies credentials or history.
set -euo pipefail
umask 077
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
PROFILE="$HOME/.dsh/profiles/web"

if (( EUID == 0 )); then
  echo 'Run as the intended DSH user, not root.' >&2
  exit 1
fi

mkdir -p -- "$PROFILE"
for name in package.json cordis.patch.yml; do
  if [[ ! -e "$PROFILE/$name" ]]; then
    install -m 600 -- "$ROOT/dotfiles/dsh/web/$name" "$PROFILE/$name"
  else
    printf 'Preserving existing profile: %s\n' "$PROFILE/$name"
  fi
done

exec python3 "$ROOT/hosts/omarchy-vm/dsh/dsh-vm" install "$@"
