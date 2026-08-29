#!/usr/bin/env bash
set -euo pipefail

source_root="${1:-$HOME/.local/share/nix-config-omarchy}"
expected_host="${OMARCHY_EXPECTED_HOST:-$(hostname -s)}"
state_dir="$HOME/.local/state/nix-config-omarchy"
vless_config="$source_root/secrets/vless/$expected_host.json"
skip_tailscale="${OMARCHY_SKIP_TAILSCALE:-false}"

die() {
  printf '[omarchy:root] ERROR: %s\n' "$*" >&2
  exit 1
}

[[ "$(hostname -s)" == "$expected_host" ]] || die "unexpected hostname"
# shellcheck disable=SC1091
source /etc/os-release
[[ "${ID:-}" == omarchy ]] || die "host is not Omarchy"
[[ -f "$vless_config" ]] || die "VLESS config missing: $vless_config"

manifests=(
  "$source_root/omarchy/packages/required.txt"
  "$source_root/omarchy/packages/extended-cli.txt"
  "$source_root/omarchy/packages/$expected_host.txt"
  "$source_root/omarchy/packages/vless.txt"
)
for manifest in "${manifests[@]}"; do
  [[ -f "$manifest" ]] || die "package manifest missing: $manifest"
done

package_output="$({
  grep -hEv '^[[:space:]]*(#|$)' "${manifests[@]}" | awk '!seen[$0]++'
} || exit 1)" || die "could not load package manifests"
mapfile -t packages <<< "$package_output"
((${#packages[@]} > 0)) || die "package manifests are empty"
aur_manifest="$source_root/omarchy/packages/aur.txt"
[[ -f "$aur_manifest" ]] || die "AUR package manifest missing: $aur_manifest"
aur_output="$(grep -Ev '^[[:space:]]*(#|$)' "$aur_manifest")" ||
  die "could not load AUR package manifest"
mapfile -t aur_packages <<< "$aur_output"
((${#aur_packages[@]} > 0)) || die "AUR package manifest is empty"

printf '[omarchy:root] Authenticate once to begin system installation.\n'
sudo -v
while sleep 45; do
  sudo -n true || exit
done 2>/dev/null &
sudo_keepalive_pid=$!
cleanup() {
  kill "$sudo_keepalive_pid" >/dev/null 2>&1 || true
}
trap cleanup EXIT

omarchy pkg add "${packages[@]}"
if ! omarchy pkg aur add "${aur_packages[@]}"; then
  printf '[omarchy:root] WARNING: AUR packages could not be installed: %s\n' \
    "${aur_packages[*]}" >&2
fi
if [[ "$skip_tailscale" == true ]]; then
  printf '[omarchy:root] Tailscale login skipped; package and daemon remain installed.\n'
else
  if [[ "$(tailscale status --json 2>/dev/null | jq -r '.BackendState // ""')" != Running ]]; then
    sudo systemctl enable tailscaled.service
    sudo systemctl restart tailscaled.service
    sudo tailscale up --accept-routes --accept-dns=false
  fi
  sudo tailscale set --operator="$USER" --accept-routes=true --accept-dns=false
  systemctl --user enable --now omarchy-tailscale-receive.service
fi

bash "$source_root/scripts/omarchy-install-vless.sh" "$vless_config"
bash "$source_root/scripts/omarchy-test-vless.sh"
OMARCHY_EXPECTED_HOST="$expected_host" \
  bash "$source_root/scripts/omarchy-install-gui.sh" "$source_root"

install -Dm0644 /dev/null "$state_dir/root-phase-complete"
printf '[omarchy:root] System and GUI installation completed successfully.\n'
