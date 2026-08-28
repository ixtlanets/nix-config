#!/usr/bin/env bash
set -uo pipefail

source_root="${1:-$HOME/.local/share/nix-config-omarchy}"
expected_host="${OMARCHY_EXPECTED_HOST:-$(hostname -s)}"
state_dir="$HOME/.local/state/nix-config-omarchy"
log_file="$state_dir/root-phase.log"
mkdir -p "$state_dir"

printf 'Zenbook Omarchy provisioning\n'
printf 'The password prompt below is local to this terminal.\n\n'

OMARCHY_EXPECTED_HOST="$expected_host" \
  bash "$source_root/scripts/omarchy-root-phase.sh" "$source_root" \
  2>&1 | tee "$log_file"
status=${PIPESTATUS[0]}

if ((status == 0)); then
  printf '\nProvisioning completed. This window will close in 5 seconds.\n'
  sleep 5
else
  printf '\nProvisioning stopped with status %d.\n' "$status"
  read -r -p 'Press Enter to close this window.' _
fi
exit "$status"
