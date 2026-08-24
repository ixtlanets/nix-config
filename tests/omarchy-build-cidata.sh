#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
builder="$repo_root/scripts/omarchy-build-cidata.sh"
tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  exit 1
}

password='test password with spaces'
printf '%s\n' "$password" > "$tmp_dir/password"
cat > "$tmp_dir/ssh" <<'EOF'
#!/usr/bin/env bash
cat <<'JSON'
{
  "blockdevices": [{
    "path": "/dev/nvme0n1",
    "size": 512110190592,
    "type": "disk",
    "model": "Micron MTFDHBA512TDV",
    "serial": "20362B0F0DBD"
  }]
}
JSON
EOF
chmod +x "$tmp_dir/ssh"
export SSH_BIN="$tmp_dir/ssh"

build_args=(
  --confirm-disk /dev/nvme0n1 \
  --output-root "$tmp_dir/output" \
  --password-file "$tmp_dir/password"
)
if [[ ${TEST_BUILD_ISO:-0} != 1 ]]; then
  build_args+=(--no-iso)
fi

"$builder" x1carbon "${build_args[@]}"

payload="$tmp_dir/output/x1carbon"
config="$payload/user_configuration.json"
credentials="$payload/user_credentials.json"

for file in \
  authorized_keys \
  manifest.txt \
  user_configuration.json \
  user_credentials.json \
  user_email_address.txt \
  user_encrypt_installation.txt \
  user_full_name.txt; do
  [[ -f "$payload/$file" ]] || fail "missing $file"
done

jq -e '
  .hostname == "x1carbon" and
  .timezone == "Europe/Moscow" and
  .locale_config.kb_layout == "us" and
  .locale_config.sys_lang == "en_US.UTF-8" and
  .omarchy_install.mode == "full_disk" and
  .disk_config.device_modifications[0].device == "/dev/nvme0n1" and
  .disk_config.device_modifications[0].wipe == true and
  .disk_config.device_modifications[0].partitions[0].size.value == 2147483648 and
  .disk_config.device_modifications[0].partitions[1].size.value == 509960257536 and
  .disk_config.disk_encryption.encryption_type == "luks" and
  .disk_config.disk_encryption.encryption_password == "test password with spaces"
' "$config" >/dev/null || fail "configuration does not match x1carbon profile"

jq -e '
  .users == [{
    "enc_password": .root_enc_password,
    "groups": [],
    "sudo": true,
    "username": "nik"
  }] and
  .encryption_password == "test password with spaces" and
  (.root_enc_password | startswith("$6$") and (endswith("\n") | not))
' "$credentials" >/dev/null || fail "credentials do not match user contract"

[[ "$(wc -l < "$payload/authorized_keys")" -eq 2 ]] ||
  fail "authorized_keys must contain both current public keys"
grep -Fq 'Micron MTFDHBA512TDV' "$payload/manifest.txt" ||
  fail "manifest does not identify target model"
grep -Fq '20362B0F0DBD' "$payload/manifest.txt" ||
  fail "manifest does not identify target serial"
[[ "$("$repo_root/scripts/omarchy-build-cidata.sh" --help 2>&1)" == *'DESTRUCTIVE'* ]] ||
  fail "help does not warn about destructive install"

if [[ ${TEST_BUILD_ISO:-0} == 1 ]]; then
  pvd_info=""
  [[ -f "$payload/cidata.iso" ]] || fail "ISO build did not create cidata.iso"
  pvd_info="$(xorriso -indev "$payload/cidata.iso" -pvd_info 2>&1)"
  if [[ "$pvd_info" != *"Volume Id    : cidata"* ]]; then
    printf '%s\n' "$pvd_info" >&2
    fail "ISO volume label is not cidata"
  fi
fi

if "$builder" x1carbon \
  --confirm-disk /dev/sda \
  --no-iso \
  --output-root "$tmp_dir/rejected" \
  --password-file "$tmp_dir/password" \
  >"$tmp_dir/rejected.stdout" 2>"$tmp_dir/rejected.stderr"; then
  fail "wrong disk confirmation unexpectedly succeeded"
fi
grep -Fq 'does not match profile target /dev/nvme0n1' "$tmp_dir/rejected.stderr" ||
  fail "wrong disk confirmation returned wrong diagnostic"
[[ ! -e "$tmp_dir/rejected/x1carbon/user_configuration.json" ]] ||
  fail "rejected build wrote destructive configuration"

cat > "$tmp_dir/ssh-wrong-disk" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' '{"blockdevices":[{"path":"/dev/nvme0n1","size":512110190592,"type":"disk","model":"Micron MTFDHBA512TDV","serial":"WRONG"}]}'
EOF
chmod +x "$tmp_dir/ssh-wrong-disk"
if SSH_BIN="$tmp_dir/ssh-wrong-disk" "$builder" x1carbon \
  --confirm-disk /dev/nvme0n1 \
  --no-iso \
  --output-root "$tmp_dir/wrong-disk" \
  --password-file "$tmp_dir/password" \
  >"$tmp_dir/wrong-disk.stdout" 2>"$tmp_dir/wrong-disk.stderr"; then
  fail "live disk identity mismatch unexpectedly succeeded"
fi
grep -Fq 'live target serial WRONG does not match profile 20362B0F0DBD' \
  "$tmp_dir/wrong-disk.stderr" || fail "disk identity mismatch returned wrong diagnostic"
[[ ! -e "$tmp_dir/wrong-disk/x1carbon/user_configuration.json" ]] ||
  fail "disk identity mismatch wrote destructive configuration"

printf 'PASS: Omarchy cidata CLI builds guarded x1carbon payload\n'
