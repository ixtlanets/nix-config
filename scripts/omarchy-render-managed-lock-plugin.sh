#!/usr/bin/env bash
set -euo pipefail

source_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
destination="${1:-}"
omarchy_path="${OMARCHY_PATH:-/usr/share/omarchy}"
source_dir="$omarchy_path/shell/plugins/lock"
patch_file="$source_root/dotfiles/omarchy/plugins/nik.lock/LockView.patch"

die() {
  printf '[omarchy:lock-render] ERROR: %s\n' "$*" >&2
  exit 1
}

[[ -n "$destination" ]] || die "usage: ${0##*/} DESTINATION"
[[ -d "$source_dir" ]] || die "built-in lock plugin is missing: $source_dir"
[[ -f "$patch_file" ]] || die "lock plugin patch is missing: $patch_file"
[[ -d "$destination" ]] || die "destination directory is missing: $destination"
[[ -z "$(find "$destination" -mindepth 1 -print -quit)" ]] ||
  die "destination directory is not empty: $destination"

cp -aL "$source_dir/." "$destination/"
patch --directory="$destination" --strip=1 --batch --forward < "$patch_file"
jq \
  '.id = "nik.lock" |
   .name = "My Lock Screen" |
   .omarchy = ((.omarchy // {}) + { clonedFrom: "omarchy.lock" }) |
   del(.omarchy.clonePaths)' \
  "$destination/manifest.json" > "$destination/manifest.json.new"
mv "$destination/manifest.json.new" "$destination/manifest.json"
