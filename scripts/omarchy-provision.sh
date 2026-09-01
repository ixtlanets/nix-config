#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
secrets_root="$repo_root/secrets"
remote_root=".local/share/nix-config-omarchy"
install_packages=false
install_gui=false
import_gpg=false
import_syncthing=false
import_vless=false
use_pkexec=false
ssh_via_socat=false
stage_only=false
skip_tailscale=false

usage() {
  cat <<'EOF'
Usage: scripts/omarchy-provision.sh [options] USER@HOST

Options:
  --install-packages  Install package manifests through Omarchy (interactive).
  --install-gui       Install GUI applications and managed browser extensions.
  --import-gpg        Transfer/import repo GPG key material, then delete staging.
  --import-syncthing  Restore the target host's Syncthing device identity.
  --import-vless      Install the target host's sing-box config and service.
  --pkexec            Show graphical polkit prompts instead of terminal sudo.
  --ssh-via-socat     Proxy SSH and rsync through socat (for local TUN conflicts).
  --stage-only         Transfer scripts/configs and requested VLESS secret, then stop.
  --skip-tailscale     Do not require a connected Tailscale node during verification.
  --secrets-root DIR  Read already-decrypted secrets from DIR.
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
    --pkexec)
      use_pkexec=true
      shift
      ;;
    --ssh-via-socat)
      ssh_via_socat=true
      shift
      ;;
    --stage-only)
      stage_only=true
      shift
      ;;
    --skip-tailscale)
      skip_tailscale=true
      shift
      ;;
    --secrets-root)
      (($# >= 2)) || die "--secrets-root requires a directory"
      secrets_root="$2"
      shift 2
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
[[ -d "$secrets_root" ]] || die "secrets root missing: $secrets_root"

control_path="/tmp/omarchy-provision-ssh-$$"
ssh_args=(
  -o ControlMaster=auto
  -o ControlPersist=60
  -o "ControlPath=$control_path"
)
rsync_ssh="ssh -o ControlMaster=auto -o ControlPersist=60 -o ControlPath=$control_path"
if $ssh_via_socat; then
  command -v socat >/dev/null 2>&1 || die "socat is required for --ssh-via-socat"
  ssh_args+=(-o 'ProxyCommand=socat - TCP:%h:%p')
  rsync_ssh+=" -o 'ProxyCommand=socat - TCP:%h:%p'"
fi

ssh_remote() {
  # Local expansion is intentional: callers pass the remote command as args.
  # shellcheck disable=SC2029
  ssh "${ssh_args[@]}" "$target" "$@"
}

rsync_remote() {
  rsync -e "$rsync_ssh" "$@"
}

close_control_master() {
  ssh "${ssh_args[@]}" -O exit "$target" >/dev/null 2>&1 || true
}
trap close_control_master EXIT

target_user="${target%@*}"
remote_host="$(ssh_remote 'hostname -s')" || die "could not read target hostname"
[[ "$remote_host" =~ ^[A-Za-z0-9][A-Za-z0-9-]*$ ]] ||
  die "target returned invalid hostname: $remote_host"

# Validate destination before package changes or secret transfer.
# shellcheck disable=SC2029
ssh_remote "[[ \$(hostname -s) == '$remote_host' ]] && [[ \$(id -un) == '$target_user' ]] && source /etc/os-release && [[ \$ID == omarchy ]] && command -v omarchy >/dev/null" ||
  die "target validation failed"
if $use_pkexec; then
  ssh_remote "command -v pkexec >/dev/null" || die "pkexec is missing on target"
fi

remote_command_prefix=""
if $use_pkexec; then
  remote_command_prefix="env PATH='$remote_root/pkexec-bin':\$PATH "
fi

run_privileged_remote() {
  local command="$1"
  if $use_pkexec; then
    ssh_remote "${remote_command_prefix}${command}"
  else
    ssh "${ssh_args[@]}" -t "$target" "$command"
  fi
}

if $import_syncthing; then
  syncthing_secret_dir="$secrets_root/syncthing/$remote_host"
  [[ -f "$syncthing_secret_dir/cert.pem" && -f "$syncthing_secret_dir/key.pem" ]] ||
    die "Syncthing identity missing: $syncthing_secret_dir"
fi
if $import_vless; then
  vless_config="$secrets_root/vless/$remote_host.json"
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
aur_manifest="$repo_root/omarchy/packages/aur.txt"
aur_output="$(grep -Ev '^[[:space:]]*(#|$)' "$aur_manifest")" ||
  die "could not load AUR package manifest"
mapfile -t aur_packages <<< "$aur_output"
((${#aur_packages[@]} > 0)) || die "AUR package manifest is empty"

# Local expansion is intentional; remote_root is a fixed script constant.
# shellcheck disable=SC2029
ssh_remote "mkdir -p '$remote_root/scripts' '$remote_root/dotfiles' '$remote_root/omarchy/packages' '$remote_root/pkexec-bin'"
rsync_remote -a --delete "$repo_root/dotfiles/omarchy/" "$target:$remote_root/dotfiles/omarchy/"
rsync_remote -a "$repo_root/dotfiles/quotes.txt" "$target:$remote_root/dotfiles/quotes.txt"
rsync_remote -a --delete "$repo_root/omarchy/packages/" "$target:$remote_root/omarchy/packages/"
rsync_remote -a "$repo_root/omarchy/plugins.tsv" "$target:$remote_root/omarchy/plugins.tsv"
rsync_remote -a \
  "$repo_root/scripts/omarchy-apply-user.sh" \
  "$repo_root/scripts/omarchy-configure-syncthing.sh" \
  "$repo_root/scripts/omarchy-enable-voxtype.sh" \
  "$repo_root/scripts/omarchy-install-gui.sh" \
  "$repo_root/scripts/omarchy-install-vless.sh" \
  "$repo_root/scripts/omarchy-root-phase.sh" \
  "$repo_root/scripts/omarchy-root-phase-terminal.sh" \
  "$repo_root/scripts/omarchy-test-vless.sh" \
  "$repo_root/scripts/omarchy-verify.sh" \
  "$target:$remote_root/scripts/"
if $use_pkexec; then
  rsync_remote -a "$repo_root/scripts/omarchy-pkexec-sudo" "$target:$remote_root/pkexec-bin/sudo"
  ssh_remote "chmod 0755 '$remote_root/pkexec-bin/sudo'"
fi

if $import_vless; then
  # shellcheck disable=SC2029
  ssh_remote "install -d -m 700 '$remote_root/secrets/vless'"
  rsync_remote -a --chmod=F600 \
    "$vless_config" \
    "$target:$remote_root/secrets/vless/"
fi

if $stage_only; then
  printf 'Omarchy provisioning files staged on %s:%s\n' "$target" "$remote_root"
  exit 0
fi

if $install_packages; then
  printf -v package_command '%q ' "${packages[@]}"
  run_privileged_remote "omarchy pkg add $package_command"
  printf -v aur_package_command '%q ' "${aur_packages[@]}"
  if ! run_privileged_remote "omarchy pkg aur add $aur_package_command"; then
    printf 'WARNING: AUR packages could not be installed: %s\n' "${aur_packages[*]}" >&2
  fi
  if [[ "$(ssh_remote "tailscale status --json 2>/dev/null | jq -r '.BackendState // \"\"'")" != Running ]]; then
    run_privileged_remote "omarchy install service tailscale"
  fi
else
  printf 'Package install skipped. Run interactively when ready:\n  omarchy pkg add'
  printf ' %q' "${packages[@]}"
  printf '\n'
  printf 'AUR package install skipped. Run interactively when ready:\n  omarchy pkg aur add'
  printf ' %q' "${aur_packages[@]}"
  printf '\n'
fi

if $import_vless; then
  # shellcheck disable=SC2029
  if ! run_privileged_remote "bash '$remote_root/scripts/omarchy-install-vless.sh' '$remote_root/secrets/vless/$remote_host.json'"; then
    # shellcheck disable=SC2029
    ssh_remote "rm -f '$remote_root/secrets/vless/$remote_host.json'"
    die "VLESS installation failed"
  fi
  run_privileged_remote "bash '$remote_root/scripts/omarchy-test-vless.sh'"
fi

if $install_gui; then
  # shellcheck disable=SC2029
  run_privileged_remote "OMARCHY_EXPECTED_HOST='$remote_host' bash '$remote_root/scripts/omarchy-install-gui.sh' '$remote_root'"
fi

if $import_gpg; then
  ssh_remote "gpg --batch --import" < "$secrets_root/gpg/public.key"
  ssh_remote "gpg --batch --import" < "$secrets_root/gpg/private.key"
  ssh_remote "gpg --batch --import-ownertrust" < "$secrets_root/gpg/ownertrust.txt"
fi

# Syncthing reads this XDG state path by default on current Arch builds.
if $import_syncthing; then
  ssh_remote "install -d -m 700 '.local/state/syncthing'"
  rsync_remote -a --chmod=F600 \
    "$syncthing_secret_dir/cert.pem" \
    "$syncthing_secret_dir/key.pem" \
    "$target:.local/state/syncthing/"
fi

# shellcheck disable=SC2029
ssh_remote "OMARCHY_EXPECTED_HOST='$remote_host' bash '$remote_root/scripts/omarchy-apply-user.sh' '$remote_root'"
if $import_syncthing; then
  # shellcheck disable=SC2029
  ssh_remote "bash '$remote_root/scripts/omarchy-configure-syncthing.sh'"
fi
# shellcheck disable=SC2029
ssh_remote "OMARCHY_EXPECTED_HOST='$remote_host' OMARCHY_SKIP_TAILSCALE='$skip_tailscale' bash '$remote_root/scripts/omarchy-verify.sh'"
