#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
root_phase="$repo_root/scripts/omarchy-root-phase.sh"
provision="$repo_root/scripts/omarchy-provision.sh"
verify="$repo_root/scripts/omarchy-verify.sh"
install="$repo_root/install.sh"

grep -Fq 'sudo tailscale up --accept-routes --accept-dns=true' "$root_phase"
grep -Fq 'sudo tailscale set --operator="$USER" --accept-routes=true --accept-dns=true' "$root_phase"
! grep -Fq -- '--accept-dns=false' "$root_phase"
grep -Fq 'sudo tailscale set --accept-dns=true' "$provision"
grep -Fq 'sudo tailscale set --accept-dns=true' "$install"
grep -Fq 'tailscale_backend_state()' "$install"
[[ "$(grep -Fc 'tailscale status --json --peers=false' "$install")" -eq 1 ]]
enable_service_line="$(grep -nFx '  enable_tailscale_service' "$install" | cut -d: -f1)"
configure_dns_line="$(grep -nFx '  configure_tailscale_dns' "$install" | cut -d: -f1)"
((configure_dns_line > enable_service_line))

grep -Fq '.TailscaleDNS == true' "$verify"
grep -Fq 'command -v tailscale >/dev/null 2>&1 || fail "tailscale is missing"' "$verify"
grep -Fq 'getent ahostsv4 "$tailscale_dns"' "$verify"
grep -Fq 'getent ahostsv4 "$tailscale_peer_short"' "$verify"

printf 'PASS: Omarchy provisioning enables and verifies Tailscale MagicDNS\n'
