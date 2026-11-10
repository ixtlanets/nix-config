#!/usr/bin/env bash
# Run as root ON PHYSICAL PVE after installing/authenticating Tailscale.
set -euo pipefail

here=$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
[[ $EUID == 0 ]] || { echo 'Run on physical PVE as root' >&2; exit 1; }
[[ $(hostname) == pve-um790 ]] || { echo 'Wrong host' >&2; exit 1; }
ip=${1:?usage: deploy.sh <PVE-Tailscale-IPv4>}
python3 - "$ip" <<'PY'
import ipaddress, sys
ip = ipaddress.IPv4Address(sys.argv[1])
assert ip in ipaddress.IPv4Network('100.64.0.0/10'), 'Not a Tailscale IPv4'
PY
[[ $(tailscale ip -4) == "$ip" ]] || { echo 'Address does not match this PVE node' >&2; exit 1; }
[[ -x /usr/lib/systemd/systemd-socket-proxyd ]]
systemctl is-active --quiet pve-guest-vpn.service
curl -fsS --proxy http://10.77.6.1:2081 --connect-timeout 5 --max-time 15 'https://controlplane.tailscale.com/key?v=130' -o /dev/null
# Check before changing any live rules. nft applies the replacement atomically.
nft -c -f "$here/pve-private-access.nft"
install -m 0644 "$here/pve-private-access.nft" /etc/pve-private-access.nft
install -m 0644 "$here/pve-private-access-firewall.service" /etc/systemd/system/
install -m 0644 "$here/pve-private-https.service" /etc/systemd/system/
install -d -m 0755 /etc/systemd/system/tailscaled.service.d
install -m 0644 "$here/tailscaled-private-access.conf" /etc/systemd/system/tailscaled.service.d/private-access.conf
vpn_changed=0
cmp -s "$here/tailscaled-vpn-egress.conf" /etc/systemd/system/tailscaled.service.d/vpn-egress.conf || vpn_changed=1
install -m 0644 "$here/tailscaled-vpn-egress.conf" /etc/systemd/system/tailscaled.service.d/vpn-egress.conf
socket_changed=0
cmp -s <(sed "s/@TAILSCALE_IPV4@/$ip/g" "$here/pve-private-https.socket.in") /etc/systemd/system/pve-private-https.socket || socket_changed=1
sed "s/@TAILSCALE_IPV4@/$ip/g" "$here/pve-private-https.socket.in" > /etc/systemd/system/pve-private-https.socket
chmod 0644 /etc/systemd/system/pve-private-https.socket
systemd-analyze verify /etc/systemd/system/pve-private-access-firewall.service /etc/systemd/system/pve-private-https.socket /etc/systemd/system/pve-private-https.service
systemctl daemon-reload
systemctl enable pve-private-access-firewall.service
# Reload an active policy atomically without restarting its dependent tailscaled.
systemctl reload-or-restart pve-private-access-firewall.service
if [[ $vpn_changed == 1 ]]; then
  systemctl restart tailscaled.service
fi
systemctl enable pve-private-https.socket
if [[ $socket_changed == 1 ]]; then
  # An active proxy retains a duplicate listening FD; stop it before rebinding.
  systemctl stop pve-private-https.service
  systemctl restart pve-private-https.socket
else
  systemctl start pve-private-https.socket
fi
systemctl is-active pve-private-access-firewall.service pve-private-https.socket
ss -lnt 'sport = :443'
