#!/usr/bin/env bash
set -euo pipefail

host="$(hostname -s)"
config_path="${1:-$HOME/.local/share/nix-config-omarchy/secrets/vless/$host.json}"
service="vless-sing-box"
unit_path="/etc/systemd/system/$service.service"
installed_config="/etc/sing-box/vless.json"
interface_path="/etc/sing-box/vless-interface"
restore_path="/usr/local/libexec/vless-restore-ipv6-ra"
resolved_path="/usr/local/libexec/vless-revert-resolved"
temporary_dir="$(mktemp -d)"
service_was_active=false
trap 'rm -rf "$temporary_dir"' EXIT

die() {
  printf '[omarchy:vless] ERROR: %s\n' "$*" >&2
  exit 1
}

[[ "$host" =~ ^[A-Za-z0-9][A-Za-z0-9-]*$ ]] || die "invalid hostname: $host"
# shellcheck disable=SC1091
source /etc/os-release
[[ "${ID:-}" == omarchy ]] || die "host is not Omarchy"
[[ -f "$config_path" ]] || die "config missing: $config_path"
systemctl is-active --quiet "$service.service" && service_was_active=true
command -v sing-box >/dev/null 2>&1 || die "sing-box is not installed"
command -v jq >/dev/null 2>&1 || die "jq is not installed"
sing-box check -c "$config_path"
tun_interface="$(jq -er '[.inbounds[] | select(.type == "tun") | .interface_name][0] // empty' "$config_path")" ||
  die "VLESS config has no TUN interface"
[[ "$tun_interface" =~ ^[A-Za-z0-9][A-Za-z0-9_.+-]*$ ]] ||
  die "invalid TUN interface: $tun_interface"
((${#tun_interface} <= 15)) || die "TUN interface is longer than 15 characters"

cat > "$temporary_dir/restore-ipv6-ra" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

for interface_path in /sys/class/net/*; do
  [[ -e "$interface_path/device" ]] || continue
  accept_ra="/proc/sys/net/ipv6/conf/${interface_path##*/}/accept_ra"
  [[ -w "$accept_ra" ]] && printf '2\n' > "$accept_ra"
done
EOF

cat > "$temporary_dir/revert-resolved" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

interface="${1:?usage: vless-revert-resolved INTERFACE}"

if ! command -v resolvectl >/dev/null 2>&1 ||
  ! systemctl is-active --quiet systemd-resolved.service; then
  exit 0
fi

# sing-box registers resolved settings shortly after systemd considers it started.
for ((attempt = 0; attempt < 50; attempt++)); do
  dns="$(resolvectl dns "$interface" 2>/dev/null || true)"
  if [[ "$dns" == *:* && -n "${dns#*:}" ]]; then
    resolvectl revert "$interface"
    resolvectl flush-caches
    exit 0
  fi
  sleep 0.1
done
EOF

cat > "$temporary_dir/$service.service" <<EOF
[Unit]
Description=VLESS tunnel via sing-box
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
ExecStartPre=/usr/bin/install -Dm0400 $installed_config /run/$service/config.json
ExecStart=/usr/bin/sing-box run --disable-color -c /run/$service/config.json
ExecStartPost=$restore_path
ExecStartPost=$resolved_path $tun_interface
ExecStopPost=$restore_path
Restart=on-failure
RestartSec=5
CapabilityBoundingSet=CAP_NET_ADMIN CAP_NET_BIND_SERVICE CAP_NET_RAW CAP_SETUID CAP_SETGID
AmbientCapabilities=CAP_NET_ADMIN CAP_NET_BIND_SERVICE CAP_NET_RAW
NoNewPrivileges=true
DeviceAllow=/dev/net/tun rw
RuntimeDirectory=$service
StateDirectory=$service
LimitNOFILE=65535
LogRateLimitIntervalSec=30s
LogRateLimitBurst=200

[Install]
WantedBy=multi-user.target
EOF

sudo install -Dm0400 "$config_path" "$installed_config"
printf '%s\n' "$tun_interface" > "$temporary_dir/vless-interface"
sudo install -Dm0444 "$temporary_dir/vless-interface" "$interface_path"
sudo install -Dm0755 "$temporary_dir/restore-ipv6-ra" "$restore_path"
sudo install -Dm0755 "$temporary_dir/revert-resolved" "$resolved_path"
sudo install -Dm0644 "$temporary_dir/$service.service" "$unit_path"
sudo systemctl daemon-reload
$service_was_active && sudo systemctl restart "$service.service"
rm -f "$config_path"

printf '[omarchy:vless] installed; run vless up to connect\n'
