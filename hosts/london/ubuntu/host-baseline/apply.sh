#!/usr/bin/env bash
set -euo pipefail

remote="${REMOTE:-ubuntu@london}"
swap_file="${SWAP_FILE:-/swapfile}"
swap_size_mib="${SWAP_SIZE_MIB:-2048}"

[[ "$swap_file" =~ ^/[A-Za-z0-9._/-]+$ ]] || {
  printf 'invalid SWAP_FILE: %s\n' "$swap_file" >&2
  exit 1
}
[[ "$swap_size_mib" =~ ^[1-9][0-9]*$ ]] || {
  printf 'invalid SWAP_SIZE_MIB: %s\n' "$swap_size_mib" >&2
  exit 1
}
command -v ssh >/dev/null 2>&1 || {
  printf 'missing required local command: ssh\n' >&2
  exit 1
}

ssh "$remote" \
  "SWAP_FILE='$swap_file' SWAP_SIZE_MIB='$swap_size_mib' bash -s" <<'REMOTE_SCRIPT'
set -euo pipefail

: "${SWAP_FILE:?missing SWAP_FILE}"
: "${SWAP_SIZE_MIB:?missing SWAP_SIZE_MIB}"

for command_name in awk basename blkid chmod chown dirname fallocate grep ln mktemp mkswap rm stat sudo swapon systemctl tee; do
  command -v "$command_name" >/dev/null 2>&1 || {
    printf 'missing required remote command: %s\n' "$command_name" >&2
    exit 1
  }
done

expected_size=$((SWAP_SIZE_MIB * 1024 * 1024))
fstab_entry_count=$(sudo awk -v path="$SWAP_FILE" '$1 == path { count++ } END { print count + 0 }' /etc/fstab)
fstab_canonical_count=$(sudo awk -v path="$SWAP_FILE" '
  $1 == path && NF == 6 && $2 == "none" && $3 == "swap" && $4 == "sw" && $5 == 0 && $6 == 0 {
    count++
  }
  END { print count + 0 }
' /etc/fstab)

if [[ "$fstab_entry_count" -gt 1 ]] ||
  [[ "$fstab_entry_count" -eq 1 && "$fstab_canonical_count" -ne 1 ]]; then
  printf 'refusing non-canonical or duplicate fstab entries for %s\n' "$SWAP_FILE" >&2
  exit 1
fi

if [[ -L "$SWAP_FILE" ]]; then
  printf 'refusing swap file symlink: %s\n' "$SWAP_FILE" >&2
  exit 1
elif [[ -e "$SWAP_FILE" ]]; then
  [[ -f "$SWAP_FILE" ]] || {
    printf 'refusing to replace non-regular path: %s\n' "$SWAP_FILE" >&2
    exit 1
  }

  swap_type=$(sudo blkid -p -s TYPE -o value "$SWAP_FILE" 2>/dev/null || true)
  [[ "$swap_type" == "swap" ]] || {
    printf 'refusing to overwrite existing non-swap file: %s\n' "$SWAP_FILE" >&2
    exit 1
  }

  actual_size=$(stat -c %s "$SWAP_FILE")
  [[ "$actual_size" -eq "$expected_size" ]] || {
    printf 'existing swap size is %s bytes; expected %s\n' "$actual_size" "$expected_size" >&2
    exit 1
  }
else
  swap_dir=$(dirname "$SWAP_FILE")
  swap_name=$(basename "$SWAP_FILE")
  temporary_swap=$(sudo mktemp --tmpdir="$swap_dir" ".${swap_name}.tmp.XXXXXX")
  cleanup() {
    if [[ -n "$temporary_swap" ]]; then
      sudo rm -f -- "$temporary_swap"
    fi
  }
  trap cleanup EXIT

  sudo fallocate -l "${SWAP_SIZE_MIB}M" "$temporary_swap"
  sudo chmod 0600 "$temporary_swap"
  sudo mkswap "$temporary_swap" >/dev/null
  sudo ln --no-target-directory -- "$temporary_swap" "$SWAP_FILE"
  sudo rm -- "$temporary_swap"
  temporary_swap=""
fi

sudo chown root:root "$SWAP_FILE"
sudo chmod 0600 "$SWAP_FILE"

if [[ "$fstab_entry_count" -eq 0 ]]; then
  printf '%s none swap sw 0 0\n' "$SWAP_FILE" | sudo tee -a /etc/fstab >/dev/null
fi

if ! swapon --noheadings --show=NAME | grep -Fxq "$SWAP_FILE"; then
  sudo swapon "$SWAP_FILE"
fi

sudo systemctl stop fwupd-refresh.timer 2>/dev/null || true
if [[ "$(systemctl is-enabled fwupd-refresh.timer 2>/dev/null || true)" != "masked" ]]; then
  sudo systemctl disable fwupd-refresh.timer 2>/dev/null || true
  sudo systemctl mask fwupd-refresh.timer
fi

[[ "$(systemctl is-enabled fwupd-refresh.timer 2>/dev/null || true)" == "masked" ]]
[[ "$(systemctl is-active fwupd-refresh.timer 2>/dev/null || true)" == "inactive" ]]
swapon --noheadings --show=NAME | grep -Fxq "$SWAP_FILE"

printf 'fwupd-refresh.timer: masked and inactive\n'
swapon --show
REMOTE_SCRIPT
