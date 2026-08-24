#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
remote_root=".local/share/nix-config-omarchy"
install_packages=false
install_gui=false
import_gpg=false
import_syncthing=false
import_vless=false

usage() {
  cat <<'EOF'
Usage: scripts/omarchy-provision.sh [options] USER@HOST

Options:
  --install-packages  Install package manifests through Omarchy (interactive).
  --install-gui       Install GUI applications and managed browser extensions.
  --import-gpg        Transfer/import repo GPG key material, then delete staging.
  --import-syncthing  Restore the x1carbon Syncthing device identity.
  --import-vless      Install the target host's sing-box config and service.
  -h, --help          Show help.
EOF
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

while (($# > 0)); do
  case "$1" in
    --install-packages)
      install_packages=true
      shift
      ;;
    --install-gui)
      install_gui=true
      shift
      ;;
    --import-gpg)
      import_gpg=true
      shift
      ;;
    --import-syncthing)
      import_syncthing=true
      shift
      ;;
    --import-vless)
      import_vless=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --*)
      die "unknown option: $1"
      ;;
    *)
      [[ -z "${target:-}" ]] || die "only one target is supported"
      target="$1"
      shift
      ;;
  esac
done

[[ "${target:-}" =~ ^[a-z_][a-z0-9_-]*@[A-Za-z0-9.-]+$ ]] ||
  die "target must look like user@host"
target_user="${target%@*}"
remote_host="$(ssh "$target" 'hostname -s')" || die "could not read target hostname"
[[ "$remote_host" =~ ^[A-Za-z0-9][A-Za-z0-9-]*$ ]] ||
  die "target returned invalid hostname: $remote_host"

# Validate destination before package changes or secret transfer.
# shellcheck disable=SC2029
ssh "$target" "[[ \$(hostname -s) == '$remote_host' ]] && [[ \$(id -un) == '$target_user' ]] && source /etc/os-release && [[ \$ID == omarchy ]] && command -v omarchy >/dev/null" ||
  die "target validation failed"

if $import_syncthing; then
  [[ "$remote_host" == x1carbon ]] || die "Syncthing identity import is only configured for x1carbon"
fi
if $import_vless; then
  vless_config="$repo_root/secrets/vless/$remote_host.json"
  [[ -f "$vless_config" ]] || die "VLESS config missing: $vless_config"
  command -v jq >/dev/null 2>&1 || die "jq is required to validate VLESS config"
  command -v sing-box >/dev/null 2>&1 || die "sing-box is required to validate VLESS config"
  tun_interface="$(jq -er '[.inbounds[] | select(.type == "tun") | .interface_name][0] // empty' "$vless_config")" ||
    die "VLESS config has no TUN interface: $vless_config"
  [[ "$tun_interface" =~ ^[A-Za-z0-9][A-Za-z0-9_.+-]*$ ]] ||
    die "invalid VLESS TUN interface: $tun_interface"
  ((${#tun_interface} <= 15)) || die "VLESS TUN interface is longer than 15 characters"
  sing-box check -c "$vless_config" || die "invalid VLESS config: $vless_config"
fi

package_manifests=(
  "$repo_root/omarchy/packages/required.txt"
  "$repo_root/omarchy/packages/extended-cli.txt"
)
host_manifest="$repo_root/omarchy/packages/$remote_host.txt"
[[ -f "$host_manifest" ]] && package_manifests+=("$host_manifest")
$import_vless && package_manifests+=("$repo_root/omarchy/packages/vless.txt")
package_output="$({
  grep -hEv '^[[:space:]]*(#|$)' "${package_manifests[@]}"
} || exit 1)" || die "could not load package manifests"
mapfile -t packages <<< "$package_output"
((${#packages[@]} > 0)) || die "package manifests are empty"

# Local expansion is intentional; remote_root is a fixed script constant.
# shellcheck disable=SC2029
ssh "$target" "mkdir -p '$remote_root/scripts' '$remote_root/dotfiles' '$remote_root/omarchy/packages'"
rsync -a --delete "$repo_root/dotfiles/omarchy/" "$target:$remote_root/dotfiles/omarchy/"
rsync -a --delete "$repo_root/omarchy/packages/" "$target:$remote_root/omarchy/packages/"
rsync -a \
  "$repo_root/scripts/omarchy-apply-user.sh" \
  "$repo_root/scripts/omarchy-configure-syncthing.sh" \
  "$repo_root/scripts/omarchy-install-gui.sh" \
  "$repo_root/scripts/omarchy-install-vless.sh" \
  "$repo_root/scripts/omarchy-verify.sh" \
  "$target:$remote_root/scripts/"

if $install_packages; then
  printf -v package_command '%q ' "${packages[@]}"
  ssh -t "$target" "omarchy pkg add $package_command"
  if [[ "$(ssh "$target" "tailscale status --json 2>/dev/null | jq -r '.BackendState // \"\"'")" != Running ]]; then
    ssh -t "$target" "omarchy install service tailscale"
  fi
else
  printf 'Package install skipped. Run interactively when ready:\n  omarchy pkg add'
  printf ' %q' "${packages[@]}"
  printf '\n'
fi

if $import_vless; then
  # shellcheck disable=SC2029
  ssh "$target" "install -d -m 700 '$remote_root/secrets/vless'"
  rsync -a --chmod=F600 \
    "$vless_config" \
    "$target:$remote_root/secrets/vless/"
  # shellcheck disable=SC2029
  if ! ssh -t "$target" "bash '$remote_root/scripts/omarchy-install-vless.sh' '$remote_root/secrets/vless/$remote_host.json'"; then
    # shellcheck disable=SC2029
    ssh "$target" "rm -f '$remote_root/secrets/vless/$remote_host.json'"
    die "VLESS installation failed"
  fi
fi

if $install_gui; then
  # shellcheck disable=SC2029
  ssh -t "$target" "OMARCHY_EXPECTED_HOST='$remote_host' bash '$remote_root/scripts/omarchy-install-gui.sh' '$remote_root'"
fi

if $import_gpg; then
  ssh "$target" "gpg --batch --import" < "$repo_root/secrets/gpg/public.key"
  ssh "$target" "gpg --batch --import" < "$repo_root/secrets/gpg/private.key"
  ssh "$target" "gpg --batch --import-ownertrust" < "$repo_root/secrets/gpg/ownertrust.txt"
fi

# Syncthing reads this XDG state path by default on current Arch builds.
if $import_syncthing; then
  ssh "$target" "install -d -m 700 '.local/state/syncthing'"
  rsync -a --chmod=F600 \
    "$repo_root/secrets/syncthing/x1carbon/cert.pem" \
    "$repo_root/secrets/syncthing/x1carbon/key.pem" \
    "$target:.local/state/syncthing/"
fi

# shellcheck disable=SC2029
ssh "$target" "OMARCHY_EXPECTED_HOST='$remote_host' bash '$remote_root/scripts/omarchy-apply-user.sh' '$remote_root'"
if [[ "$remote_host" == x1carbon ]]; then
  # shellcheck disable=SC2029
  ssh "$target" "bash '$remote_root/scripts/omarchy-configure-syncthing.sh'"
fi
# shellcheck disable=SC2029
ssh "$target" "OMARCHY_EXPECTED_HOST='$remote_host' bash '$remote_root/scripts/omarchy-verify.sh'"
