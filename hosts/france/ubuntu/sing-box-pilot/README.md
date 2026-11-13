# Additive sing-box subscription pilot

One independent native VLESS Reality service per host. France uses
`194.87.166.59:443/TCP`; Frankfurt uses `31.58.85.163:34443/TCP`;
Poland uses `193.124.205.153:34443/TCP`; Italy uses
`81.29.155.74:34443/TCP`. Italy's port is provisional pending host inventory
and a free-port check. These are source-supported candidates, not evidence of
installation or acceptance. This change is stage-only; production acceptance
for the expansion is unperformed. The owner's intended general pool is an equal
four-node URLTest pool (France, Frankfurt, Poland, Italy), not reserve tiers;
this server bundle does not publish or configure that client pool.

Poland's existing public TCP 22/80/443/24443 and loopback 8443/8444 services
must remain untouched. Only the additive `nikcode-singbox-pilot` is in scope.
No Docker, TUN, forwarding, firewall, routing or existing-service changes.

## Private inputs

The owner already provisioned `pass nikcode.xyz/config/pilot-state` and
`pass nikcode.xyz/config/pilot-node-keys`. Do not initialize or rotate them.
The state is also at
`~/.local/state/nikcode-singbox-pilot-20261112/pilot-state.json`.

`render.py` reads the subscription state (`nodes`, `devices`) and a separate
private keys JSON mapping each selected node (`france`, `frankfurt`, `poland`,
`italy`) to `private_key`, `public_key`. Actual encrypted state must be prepared
and reviewed by the owner; source support does not imply those entries exist.
It reuses enabled device `credentials[node_id].uuid` exactly and checks the
public key matches. Optional `--canary-uuid` is an additional private test user,
never published in subscriptions. Output must be outside this repository.

```sh
python3 render.py --state /private/pilot-state.json --keys /private/node-keys.json \
  --node france --output /private/france-server.json --canary-uuid UUID
/verified/sing-box check -c /private/france-server.json
```

The TLS handshake target is state `server_name`, currently `www.google.com:443`.
The parent verified TLS1.3/X25519/certificate validity from France and Frankfurt
before their provisioning; no such verification is claimed for Poland or Italy. Private/LAN destination addresses are rejected by server routing.
Users use `xtls-rprx-vision`, including the optional canary. Domain destinations
are resolved before rejecting private, CGNAT/Tailscale and multicast addresses.

## Pinned installation, stage only

Use the official archive and hashes in [pin.json](pin.json), verified by the
parent; core `1.14.4`, linux-amd64, CGO disabled. Do not copy Arch's dynamically
linked `/usr/bin/sing-box` to Ubuntu.

Transfer this bundle, the verified binary and the private rendered config to a
root-only staging directory. As root on the selected host:

```sh
bash /private/stage/install.sh /private/stage/sing-box /private/stage/server.json
systemd-analyze verify /etc/systemd/system/nikcode-singbox-pilot.service
```

Installer verifies the exact binary hash, config, local address and free TCP
port; creates only its dedicated system user and paths, and runs daemon-reload.
It **does not start or enable** the unit. An identical re-run is a no-op;
different existing pilot files are refused, so updates cannot silently replace
a running configuration. It does not modify firewall policies or old services.

New paths: `/opt/nikcode-singbox-pilot/sing-box`,
`/etc/nikcode-singbox-pilot/config.json` (root:pilot-group `0640`, directory `0750`),
`/etc/systemd/system/nikcode-singbox-pilot.service`.

The sandbox permits `AF_NETLINK` for sing-box's network monitor even without TUN.
Omitting it caused an observed immediate startup failure: `create netlink socket:
address family not supported by protocol`. `CAP_NET_ADMIN` remains absent.
Warn-level stderr goes to the journal so startup failures remain observable;
credentials and full configs must never be printed in diagnostics.

After parent review and protected baseline capture, start **only the new unit**:

```sh
systemctl start nikcode-singbox-pilot.service
systemctl show nikcode-singbox-pilot.service -p ActiveState -p SubState -p MainPID -p NRestarts
```

Perform actual per-node isolated SOCKS DNS/HTTPS/exit-IP and reconnect tests
through the physical home interface before enabling or publishing. Repeat the
baseline and verify old traffic. Enable only after acceptance. Rollback stops
and disables **only** `nikcode-singbox-pilot.service`; no file/account deletion
or old-service restart is required. Keep the last working private config.

## Read-only access and protected baselines

France uses owner key `~/.ssh/id_rsa_1` and existing pin file:

```sh
ssh -F /dev/null -o BatchMode=yes -o StrictHostKeyChecking=yes \
  -o UserKnownHostsFile=/home/nik/.local/state/nikcode-singbox-pilot-20261112/france-known-hosts \
  -o GlobalKnownHostsFile=/dev/null -o IdentitiesOnly=yes -i ~/.ssh/id_rsa_1 \
  root@194.87.166.59 'systemctl show awg-fr.service ssh.service -p Id -p MainPID -p NRestarts -p ActiveState; ss -lntup'
ssh -o BatchMode=yes -o StrictHostKeyChecking=yes frankfurt \
  'systemctl show awg-s22-test.service docker.service tailscaled.service -p Id -p MainPID -p NRestarts -p ActiveState; docker ps --format "{{.Names}} {{.ID}} {{.Ports}}"; ss -lntup'
```

Also compare private snapshots of `ip -j address`, `ip -j route show table all`,
`ip -j rule`, `iptables-save`, `ip6tables-save` before/after. Expected protected
PIDs during reconnaissance: France AWG1488, SSH855; Frankfurt AWG1177289,
Docker962, Tailscale758; all observed `NRestarts=0`. Re-read before deployment;
these are observations, not permanent expected IDs. Preserve Warsaw and London.

The parent persists the previously accepted France pin at the path above before
deployment; do not replace it with an unverified scan.

```sh
PYTHONDONTWRITEBYTECODE=1 SING_BOX_BIN=/verified/sing-box \
  python3 -m unittest discover -s hosts/france/ubuntu/sing-box-pilot -p 'test_*.py'
bash -n hosts/france/ubuntu/sing-box-pilot/install.sh
```
