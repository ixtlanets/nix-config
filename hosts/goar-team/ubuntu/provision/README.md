# goar-team provisioning

Local SSH apply bundle for a dedicated Ubuntu 24.04 VLESS+Reality VPS.
Run from a checkout with OpenSSH, the repo helper and access to the VPS as root:

```sh
REMOTE=root@<IP> SSH_KEY="$HOME/.ssh/id_rsa_1" \
  hosts/goar-team/ubuntu/provision/provision.sh
```

`REMOTE` is required; there is no live-host default. `SSH_KEY` is optional.
`REALITY_DOMAIN` defaults to `www.google.com`, `REALITY_PORT` to `443`.
These settings apply only on the first installation. Existing Reality state is
preserved, including when an interrupted installation left the directory present.
Inspect and repair partial state manually; the script will not delete it.

The script checks Ubuntu and dependencies, installs missing curl/jq/python3,
Docker using its official installer, Compose plugin if absent, and reality-ezpz
only when `/opt/reality-ezpz` is absent. It installs the repo's `reality-user`
helper atomically when bytes change and verifies the engine container is running.
Existing Docker installations are kept; if their apt repositories cannot supply
`docker-compose-plugin`, the operator must fix the repository and rerun.

Tailscale is installed if missing and its daemon enabled. A connected node is
left alone. Supply `TAILSCALE_AUTHKEY` through the local environment for initial
join; it is sent via SSH stdin and the printed command redacts the key. Without
a key the join is skipped with a warning, while provisioning continues. An
operator can later run `tailscale up --hostname=goar-team --auth-key=<key>` on
this VPS. Do not capture keys or generated user URLs in public logs.

The human creates/pays for the VM, records its IP, verifies the SSH host key,
obtains the tailnet key, applies the baseline and firewall policy, validates
VLESS from a client, and captures the encrypted DR bundle. See the
[runbook](../../../../docs/goar-team-vless-node.md).

The upstream installer is downloaded at apply time and can change. Its current
image may differ from the DR target `gzxhwq/sing-box:1.13.5`; inspect and validate
image/config compatibility before accepting the deployment. Never blindly bump
the image or regenerate an existing identity. This bundle has not been executed
against a live host; a running container alone does not prove client connectivity.
