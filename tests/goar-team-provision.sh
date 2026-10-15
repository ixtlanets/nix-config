#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
provision="$repo_root/hosts/goar-team/ubuntu/provision/provision.sh"
[[ -x "$provision" ]] || { printf 'FAIL: provision.sh must exist and be executable\n' >&2; exit 1; }
bash -n "$provision"
printf 'PASS: provisioning entry point exists and parses\n'
for artifact in \
  hosts/goar-team/ubuntu/provision/README.md \
  hosts/goar-team/ubuntu/host-baseline/apply.sh \
  hosts/goar-team/ubuntu/host-baseline/README.md \
  secrets/proxy/goar-team/README.md \
  docs/goar-team-vless-node.md; do
  [[ -f "$repo_root/$artifact" ]] || { printf 'FAIL: missing %s\n' "$artifact" >&2; exit 1; }
done
baseline="$repo_root/hosts/goar-team/ubuntu/host-baseline/apply.sh"
[[ -x "$baseline" ]]
bash -n "$baseline"
grep -Fq '[[ ! -e /opt/reality-ezpz && ! -L /opt/reality-ezpz ]]' "$provision"
grep -Fq 'if ! command -v docker >/dev/null; then' "$provision"
for field in config engine.conf docker-compose.yml users notes.md private_key short_id UUIDs gzxhwq/sing-box:1.13.5; do
  grep -Fq "$field" "$repo_root/secrets/proxy/goar-team/README.md" || { printf 'FAIL: missing DR field %s\n' "$field" >&2; exit 1; }
done
grep -Fq '### goar-team' "$repo_root/docs/proxy-setup.md"
printf 'PASS: goar-team artifacts, installation guards and DR inventory\n'
