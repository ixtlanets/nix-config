#!/usr/bin/env bash
set -euo pipefail

archive=${1:-}
target=${2:-}

if [[ -z "$archive" || -z "$target" ]]; then
  echo "usage: $0 <backup.tar.zst.age> <target-dir>" >&2
  exit 1
fi

: "${AGE_IDENTITY_FILE:?set AGE_IDENTITY_FILE to the private age identity path}"

for command in age tar zstd; do
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "missing required command: $command" >&2
    exit 1
  fi
done

install -d -m 0700 "$target"
age -d -i "$AGE_IDENTITY_FILE" "$archive" | zstd -d | tar -C "$target" -xf -

echo "$target"
