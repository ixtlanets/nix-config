#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
module="$repo_root/modules/home-manager/transcribe-media-script.nix"
common="$repo_root/modules/home-manager/common.nix"

[[ -f "$module" ]] || {
  printf 'Missing Home Manager module: %s\n' "$module" >&2
  exit 1
}
grep -Fq './transcribe-media-script.nix' "$common" || {
  printf 'common.nix does not import transcribe-media-script.nix\n' >&2
  exit 1
}
grep -Fq 'dotfiles/omarchy/bin/transcribe-media' "$module" || {
  printf 'transcribe-media module does not package the tested helper script\n' >&2
  exit 1
}

printf 'PASS: Home Manager packages transcribe-media on macOS\n'
