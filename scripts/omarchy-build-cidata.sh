#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage() {
  cat <<'EOF'
Build an Omarchy Quattro cidata payload for unattended installation.

DESTRUCTIVE: booting Omarchy ISO with this payload wipes profile target disk.

Usage:
  scripts/omarchy-build-cidata.sh HOST --confirm-disk DEVICE [options]

Options:
  --confirm-disk DEVICE  Must exactly match host profile target disk.
  --no-iso               Create payload files without cidata.iso.
  --output-root DIR      Output parent (default: omarchy/output).
  --password-file FILE   Read shared user/root/LUKS password from first line.
  -h, --help             Show this help.

Without --password-file, password is read twice from controlling terminal.
EOF
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "required command not found: $1"
}

validate_profile() {
  local required=(
    HOSTNAME USERNAME FULL_NAME EMAIL_ADDRESS TIMEZONE KEYBOARD
    TARGET_DISK TARGET_DISK_SIZE_BYTES TARGET_DISK_MODEL TARGET_DISK_SERIAL
    PROBE_HOST PROBE_USER PROBE_SSH_HOST_KEY ENCRYPT_INSTALLATION
  )
  local name

  for name in "${required[@]}"; do
    [[ -n "${!name:-}" ]] || die "profile is missing $name"
  done
  [[ "$HOSTNAME" =~ ^[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?$ ]] ||
    die "invalid hostname in profile: $HOSTNAME"
  [[ "$USERNAME" =~ ^[a-z_][a-z0-9_-]*[$]?$ ]] ||
    die "invalid username in profile: $USERNAME"
  [[ "$TARGET_DISK" =~ ^/dev/(sd[a-z]+|vd[a-z]+|xvd[a-z]+|nvme[0-9]+n[0-9]+|mmcblk[0-9]+)$ ]] ||
    die "invalid whole-disk target in profile: $TARGET_DISK"
  [[ "$TARGET_DISK_SIZE_BYTES" =~ ^[0-9]+$ ]] ||
    die "invalid disk size in profile: $TARGET_DISK_SIZE_BYTES"
  ((TARGET_DISK_SIZE_BYTES >= 34 * 1024 * 1024 * 1024)) ||
    die "profile disk is smaller than Omarchy minimum"
  [[ "$ENCRYPT_INSTALLATION" == true ]] ||
    die "x1carbon profile must explicitly enable LUKS"
  [[ "$PROBE_SSH_HOST_KEY" =~ ^ssh-ed25519[[:space:]][A-Za-z0-9+/=]+$ ]] ||
    die "profile SSH host key must be a pinned Ed25519 public key"
  declare -p AUTHORIZED_KEY_FILES >/dev/null 2>&1 ||
    die "profile is missing AUTHORIZED_KEY_FILES"
  ((${#AUTHORIZED_KEY_FILES[@]} > 0)) ||
    die "profile must include at least one SSH public key"
}

verify_target_disk() {
  local known_hosts="$1"
  local facts path size type model serial

  printf '%s %s\n' "$PROBE_HOST" "$PROBE_SSH_HOST_KEY" > "$known_hosts"
  facts="$(
    "$ssh_bin" \
      -o BatchMode=yes \
      -o ConnectTimeout=10 \
      -o "GlobalKnownHostsFile=/dev/null" \
      -o "UserKnownHostsFile=$known_hosts" \
      -o StrictHostKeyChecking=yes \
      "$PROBE_USER@$PROBE_HOST" \
      "lsblk -Jbd -o PATH,SIZE,TYPE,MODEL,SERIAL '$TARGET_DISK'"
  )" || die "could not verify target disk over SSH: $PROBE_USER@$PROBE_HOST"

  jq -e '.blockdevices | length == 1' <<< "$facts" >/dev/null ||
    die "disk probe did not return exactly one device"
  path="$(jq -r '.blockdevices[0].path // ""' <<< "$facts")"
  size="$(jq -r '.blockdevices[0].size // ""' <<< "$facts")"
  type="$(jq -r '.blockdevices[0].type // ""' <<< "$facts")"
  model="$(jq -r '.blockdevices[0].model // "" | sub("[[:space:]]+$"; "")' <<< "$facts")"
  serial="$(jq -r '.blockdevices[0].serial // "" | sub("[[:space:]]+$"; "")' <<< "$facts")"

  [[ "$path" == "$TARGET_DISK" ]] ||
    die "live target path $path does not match profile $TARGET_DISK"
  [[ "$size" == "$TARGET_DISK_SIZE_BYTES" ]] ||
    die "live target size $size does not match profile $TARGET_DISK_SIZE_BYTES"
  [[ "$type" == disk ]] || die "live target is not a whole disk: $type"
  [[ "$model" == "$TARGET_DISK_MODEL" ]] ||
    die "live target model $model does not match profile $TARGET_DISK_MODEL"
  [[ "$serial" == "$TARGET_DISK_SERIAL" ]] ||
    die "live target serial $serial does not match profile $TARGET_DISK_SERIAL"
}

read_password() {
  local first second

  if [[ -n "$password_file" ]]; then
    [[ -f "$password_file" ]] || die "password file not found: $password_file"
    IFS= read -r first < "$password_file" || true
  else
    [[ -t 0 ]] || die "use --password-file when stdin is not a terminal"
    read -r -s -p 'User/root/LUKS password: ' first
    printf '\n' >&2
    read -r -s -p 'Confirm password: ' second
    printf '\n' >&2
    [[ "$first" == "$second" ]] || die "passwords do not match"
  fi

  [[ -n "$first" ]] || die "password cannot be empty"
  printf '%s' "$first"
}

hash_password() {
  local secret_file="$1"

  if command -v mkpasswd >/dev/null 2>&1; then
    mkpasswd --method=sha-512 --stdin < "$secret_file"
  elif command -v openssl >/dev/null 2>&1; then
    openssl passwd -6 -stdin < "$secret_file"
  else
    die "mkpasswd or openssl is required to hash password"
  fi
}

write_authorized_keys() {
  local destination="$1"
  local relative_path key_file line

  : > "$destination"
  for relative_path in "${AUTHORIZED_KEY_FILES[@]}"; do
    key_file="$repo_root/$relative_path"
    [[ -f "$key_file" ]] || die "SSH public key not found: $relative_path"
    while IFS= read -r line || [[ -n "$line" ]]; do
      [[ -z "$line" || "$line" == \#* ]] && continue
      [[ "$line" =~ ^(ssh-(rsa|ed25519)|ecdsa-sha2-|sk-ssh-) ]] ||
        die "invalid SSH public key in $relative_path"
      printf '%s\n' "$line" >> "$destination"
    done < "$key_file"
  done
  [[ -s "$destination" ]] || die "authorized_keys would be empty"
}

write_credentials() {
  local destination="$1"
  local secret_file="$2"
  local hash_file="$3"

  jq -n \
    --arg username "$USERNAME" \
    --rawfile password "$secret_file" \
    --rawfile password_hash "$hash_file" \
    '{
      encryption_password: $password,
      root_enc_password: $password_hash,
      users: [{
        enc_password: $password_hash,
        groups: [],
        sudo: true,
        username: $username
      }]
    }' > "$destination"
}

write_configuration() {
  local destination="$1"
  local secret_file="$2"
  local mib=$((1024 * 1024))
  local gib=$((1024 * mib))
  local disk_size_in_mib=$((TARGET_DISK_SIZE_BYTES / mib * mib))
  local boot_partition_start=$mib
  local boot_partition_size=$((2 * gib))
  local main_partition_start=$((boot_partition_start + boot_partition_size))
  local main_partition_size=$((disk_size_in_mib - main_partition_start - mib))

  ((main_partition_size >= 32 * gib)) || die "calculated root partition is too small"

  jq -n \
    --arg disk "$TARGET_DISK" \
    --arg hostname "$HOSTNAME" \
    --arg keyboard "$KEYBOARD" \
    --arg timezone "$TIMEZONE" \
    --argjson boot_partition_start "$boot_partition_start" \
    --argjson boot_partition_size "$boot_partition_size" \
    --argjson main_partition_start "$main_partition_start" \
    --argjson main_partition_size "$main_partition_size" \
    --rawfile password "$secret_file" \
    '{
      app_config: null,
      "archinstall-language": "English",
      auth_config: {},
      audio_config: {audio: "pipewire"},
      bootloader_config: {bootloader: "Limine", uki: false, removable: false},
      custom_commands: [],
      omarchy_install: {
        mode: "full_disk",
        defer_provisioning: false,
        target_mount: "/mnt",
        boot: {
          esp_mount: "/boot",
          esp_path: "/EFI/limine",
          efi_binary: "limine_x64.efi",
          enable_fallback: true
        },
        storage: {kernel: "linux"}
      },
      disk_config: {
        config_type: "default_layout",
        device_modifications: [{
          device: $disk,
          partitions: [{
            btrfs: [],
            dev_path: null,
            flags: ["boot", "esp"],
            fs_type: "fat32",
            mount_options: [],
            mountpoint: "/boot",
            obj_id: "ea21d3f2-82bb-49cc-ab5d-6f81ae94e18d",
            size: {sector_size: {unit: "B", value: 512}, unit: "B", value: $boot_partition_size},
            start: {sector_size: {unit: "B", value: 512}, unit: "B", value: $boot_partition_start},
            status: "create",
            type: "primary"
          }, {
            btrfs: [
              {mountpoint: "/", name: "@"},
              {mountpoint: "/home", name: "@home"},
              {mountpoint: "/var/log", name: "@log"},
              {mountpoint: "/var/cache/pacman/pkg", name: "@pkg"}
            ],
            dev_path: null,
            flags: [],
            fs_type: "btrfs",
            mount_options: ["compress=zstd"],
            mountpoint: null,
            obj_id: "8c2c2b92-1070-455d-b76a-56263bab24aa",
            size: {sector_size: {unit: "B", value: 512}, unit: "B", value: $main_partition_size},
            start: {sector_size: {unit: "B", value: 512}, unit: "B", value: $main_partition_start},
            status: "create",
            type: "primary"
          }],
          wipe: true
        }],
        disk_encryption: {
          encryption_type: "luks",
          lvm_volumes: [],
          iter_time: 2000,
          partitions: ["8c2c2b92-1070-455d-b76a-56263bab24aa"],
          encryption_password: $password
        }
      },
      hostname: $hostname,
      kernels: ["linux"],
      network_config: {type: "iso"},
      ntp: true,
      parallel_downloads: 8,
      script: null,
      services: [],
      swap: true,
      timezone: $timezone,
      locale_config: {kb_layout: $keyboard, sys_enc: "UTF-8", sys_lang: "en_US.UTF-8"},
      mirror_config: {
        custom_repositories: [],
        custom_servers: [
          {url: "https://mirror.omarchy.org/$repo/os/$arch"},
          {url: "https://mirror.rackspace.com/archlinux/$repo/os/$arch"},
          {url: "https://geo.mirror.pkgbuild.com/$repo/os/$arch"}
        ],
        mirror_regions: {},
        optional_repositories: []
      },
      packages: ["base-devel", "git", "omarchy-keyring", "omarchy-settings", "omarchy"],
      profile_config: {gfx_driver: null, greeter: null, profile: {}},
      version: "3.0.9"
    }' > "$destination"
}

build_iso() {
  local payload_dir="$1"
  local iso_path="$2"

  if command -v xorriso >/dev/null 2>&1; then
    xorriso -as mkisofs -quiet -o "$iso_path" -V cidata -J -r "$payload_dir"
  elif command -v genisoimage >/dev/null 2>&1; then
    genisoimage -quiet -output "$iso_path" -volid cidata -joliet -rock "$payload_dir"
  else
    die "xorriso or genisoimage is required; use --no-iso to create files only"
  fi
}

if [[ $# -eq 0 || "${1:-}" == -h || "${1:-}" == --help ]]; then
  usage
  exit 0
fi

host="$1"
shift
[[ "$host" =~ ^[a-z0-9][a-z0-9-]*$ ]] || die "invalid host profile name: $host"

confirm_disk=""
make_iso=true
output_root="$repo_root/omarchy/output"
password_file=""
ssh_bin="${SSH_BIN:-ssh}"

while (($# > 0)); do
  case "$1" in
    --confirm-disk)
      (($# >= 2)) || die "--confirm-disk requires a value"
      confirm_disk="$2"
      shift 2
      ;;
    --no-iso)
      make_iso=false
      shift
      ;;
    --output-root)
      (($# >= 2)) || die "--output-root requires a value"
      output_root="$2"
      shift 2
      ;;
    --password-file)
      (($# >= 2)) || die "--password-file requires a value"
      password_file="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "unknown option: $1"
      ;;
  esac
done

profile="$repo_root/omarchy/cidata/$host.conf"
[[ -f "$profile" ]] || die "host profile not found: omarchy/cidata/$host.conf"
# shellcheck source=/dev/null
source "$profile"

validate_profile
[[ -n "$confirm_disk" ]] || die "--confirm-disk $TARGET_DISK is required"
[[ "$confirm_disk" == "$TARGET_DISK" ]] ||
  die "confirmed disk $confirm_disk does not match profile target $TARGET_DISK"
require_command jq
require_command "$ssh_bin"

umask 077
if [[ -e "$output_root" ]]; then
  [[ -d "$output_root" && ! -L "$output_root" ]] ||
    die "output root is not a real directory: $output_root"
else
  mkdir -p "$output_root"
  chmod 700 "$output_root"
fi
output_root="$(realpath "$output_root")"
if [[ "$output_root" == "$repo_root" || "$output_root" == "$repo_root/"* ]]; then
  git -C "$repo_root" check-ignore -q "$output_root/.cidata-secret-check" ||
    die "output directory inside repository must be gitignored: $output_root"
fi
output_dir="$output_root/$host"
[[ ! -L "$output_dir" ]] || die "refusing symlink output directory: $output_dir"

staging="$(mktemp -d "$output_root/.${host}.XXXXXX")"
iso_staging="$output_root/.${host}-cidata.iso.tmp"
cleanup() {
  rm -rf -- "$staging"
  rm -f -- "$iso_staging"
}
trap cleanup EXIT

secret_file="$staging/.password"
hash_file="$staging/.password-hash"
known_hosts="$staging/.known-hosts"
verify_target_disk "$known_hosts"
rm -f -- "$known_hosts"
read_password > "$secret_file"
password_hash="$(hash_password "$secret_file")"
printf '%s' "$password_hash" > "$hash_file"

write_configuration "$staging/user_configuration.json" "$secret_file"
write_credentials "$staging/user_credentials.json" "$secret_file" "$hash_file"
printf '%s\n' "$FULL_NAME" > "$staging/user_full_name.txt"
printf '%s\n' "$EMAIL_ADDRESS" > "$staging/user_email_address.txt"
printf '%s\n' "$ENCRYPT_INSTALLATION" > "$staging/user_encrypt_installation.txt"
write_authorized_keys "$staging/authorized_keys"

rm -f -- "$secret_file" "$hash_file"
cat > "$staging/manifest.txt" <<EOF
Omarchy Quattro unattended install payload
Host: $HOSTNAME
User: $USERNAME
Target: $TARGET_DISK
Target size: $TARGET_DISK_SIZE_BYTES bytes
Target model: $TARGET_DISK_MODEL
Target serial: $TARGET_DISK_SERIAL
Encryption: LUKS, shared user/root/LUKS password
Keyboard: $KEYBOARD
Timezone: $TIMEZONE
SSH public keys: ${#AUTHORIZED_KEY_FILES[@]}
Schema source: Omarchy v4.0.0 configurator
EOF

for json_file in "$staging/user_configuration.json" "$staging/user_credentials.json"; do
  jq -e . "$json_file" >/dev/null || die "generated invalid JSON: ${json_file##*/}"
done

if $make_iso; then
  build_iso "$staging" "$iso_staging"
fi

mkdir -p "$output_dir"
chmod 700 "$output_dir"
rm -f -- \
  "$output_dir/authorized_keys" \
  "$output_dir/cidata.iso" \
  "$output_dir/manifest.txt" \
  "$output_dir/user_configuration.json" \
  "$output_dir/user_credentials.json" \
  "$output_dir/user_email_address.txt" \
  "$output_dir/user_encrypt_installation.txt" \
  "$output_dir/user_full_name.txt"
mv "$staging"/* "$output_dir"/
if $make_iso; then
  mv "$iso_staging" "$output_dir/cidata.iso"
fi
chmod 600 "$output_dir"/*

printf 'Built protected cidata payload: %s\n' "$output_dir"
printf 'Target: %s (%s bytes, %s, serial %s)\n' \
  "$TARGET_DISK" "$TARGET_DISK_SIZE_BYTES" "$TARGET_DISK_MODEL" "$TARGET_DISK_SERIAL"
if $make_iso; then
  printf 'Attach %s/cidata.iso beside official Omarchy ISO.\n' "$output_dir"
fi
