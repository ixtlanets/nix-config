#!/usr/bin/env bash
set -euo pipefail

config_path="${1:-$HOME/.local/share/nix-config-omarchy/secrets/vless/x1carbon.json}"
service="vless-sing-box"
unit_path="/etc/systemd/system/$service.service"
installed_config="/etc/sing-box/vless.json"
restore_path="/usr/local/libexec/vless-restore-ipv6-ra"
temporary_dir="$(mktemp -d)"
trap 'rm -rf "$temporary_dir"' EXIT

die() {
  printf '[omarchy:vless] ERROR: %s\n' "$*" >&2
  exit 1
}

[[ "$(hostname -s)" == x1carbon ]] || die "unexpected hostname"
# shellcheck disable=SC1091
source /etc/os-release
[[ "${ID:-}" == omarchy ]] || die "host is not Omarchy"
[[ -f "$config_path" ]] || die "config missing: $config_path"
command -v sing-box >/dev/null 2>&1 || die "sing-box is not installed"
sing-box check -c "$config_path"

cat > "$temporary_dir/restore-ipv6-ra" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

for interface_path in /sys/class/net/*; do
  [[ -e "$interface_path/device" ]] || continue
  accept_ra="/proc/sys/net/ipv6/conf/${interface_path##*/}/accept_ra"
  [[ -w "$accept_ra" ]] && printf '2\n' > "$accept_ra"
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
ExecStopPost=$restore_path
Restart=on-failure
RestartSec=5
CapabilityBoundingSet=CAP_NET_ADMIN CAP_NET_BIND_SERVICE CAP_SETUID CAP_SETGID
AmbientCapabilities=CAP_NET_ADMIN CAP_NET_BIND_SERVICE
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
sudo install -Dm0755 "$temporary_dir/restore-ipv6-ra" "$restore_path"
sudo install -Dm0644 "$temporary_dir/$service.service" "$unit_path"
sudo systemctl daemon-reload
rm -f "$config_path"

printf '[omarchy:vless] installed; run vless up to connect\n'
