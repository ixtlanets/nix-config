# UM790Pro Tailscale Subnet Router Implementation Plan

**Goal:** Make `m1max` (`192.168.1.174`) and `m3max` (`192.168.1.144`) reachable by IP, on all ports and IP protocols, from every Tailscale device while Tailscale remains stopped on both Macs.

**Architecture:** The active CachyOS installation on `um790pro` advertises two `/32` subnet routes and forwards them to its home LAN with Tailscale's default SNAT. The matching NixOS host configuration expresses the same router role. Tailnet policy grants member-owned, tagged, and shared Tailscale devices access to both addresses. Each client still has to accept subnet routes; non-Linux clients do so by default, while Linux clients are enrolled progressively after an `m1max` canary from `zenbook` over LTE.

**Safety boundary:** Do not advertise `192.168.1.0/24`, disable SNAT, disable the macOS firewall, set UFW's global forward policy to `ACCEPT`, or make `um790pro` accept its own advertised routes. Do not touch or restart the London proxy services. Never run a NixOS rebuild on the user's behalf; ask the user to run the documented rebuild commands.

**Primary files:**

- Modify: `hosts/um790pro/nixos/configuration.nix`
- Modify: `hosts/zenbook/nixos/configuration.nix`
- Modify: `hosts/x1carbon/nixos/configuration.nix`
- Modify: `hosts/m3max/nixos/configuration.nix`
- Modify: `install.sh`
- Modify: `docs/proxy-setup.md`

**External state:** DHCP reservations on the home router, the Tailscale tailnet policy, route approval in the Tailscale admin console, and Tailscale preferences on Linux devices not managed by this flake.

---

## Fixed decisions

| Decision | Value |
|---|---|
| Router | `um790pro` |
| Router primary OS | CachyOS; keep NixOS configuration equivalent |
| Routed endpoints | `m1max = 192.168.1.174/32`, `m3max = 192.168.1.144/32` |
| Client scope | All member-owned, tagged, and shared Tailscale devices |
| Network scope | All IP protocols and ports; destination services and macOS firewall still decide what answers |
| Return path | Default Tailscale subnet SNAT enabled |
| Naming | IP addresses only for the first version; existing SSH aliases may remain |
| Rollout | `m1max` canary, LTE verification, then `m3max`, then remaining Linux clients |

## Expected packet path

```text
tailnet client
  -> Tailscale tunnel
  -> um790pro tailscale0
  -> Tailscale policy check
  -> forwarding + SNAT to the current um790pro LAN address
  -> m1max 192.168.1.174 or m3max 192.168.1.144
  -> ordinary LAN reply to um790pro
  -> reverse NAT + Tailscale tunnel
```

The Macs will see the current LAN address of `um790pro` (observed as `192.168.1.241`),
not the originating `100.x` address. This is intentional: it avoids static routes on
the Macs and home router. The implementation must discover the interface/address
rather than assume `wlan0` and `.241`; reserving `.241` is recommended for predictable
logs but is not required for the return path.

---

### Task 1: Freeze addresses and capture the baseline

**Files:** None; router and runtime checks only.

- [ ] **Step 1: Create DHCP reservations**

User action in the home-router UI:

```text
m1max -> 192.168.1.174
m3max -> 192.168.1.144
```

For Wi-Fi, ensure macOS uses a stable private Wi-Fi address for this SSID rather than a rotating address.

- [ ] **Step 2: Verify both reservations from `um790pro`**

Run read-only over the existing Tailscale SSH path:

```bash
ssh um790pro 'ip -br -4 addr; ip route get 192.168.1.174; ip route get 192.168.1.144; getent hosts m1max.local m3max.local; ping -c 1 192.168.1.174; ping -c 1 192.168.1.144; ip -4 neigh show'
```

Expected: `m1max.local` resolves to `192.168.1.174`, `m3max.local` resolves to
`192.168.1.144`, and both lookups select the same home-LAN interface. Compare the
post-ping neighbor MAC addresses with the DHCP reservations in the router UI; mDNS and
the neighbor cache alone are not proof of DHCP ownership. Record the selected interface
and current `um790pro` LAN address for later packet capture/firewall diagnostics.

- [ ] **Step 3: Verify representative services before adding routing**

```bash
ssh um790pro 'for host in 192.168.1.174 192.168.1.144; do timeout 3 bash -c "</dev/tcp/${host}/22" && echo "${host}:22 open"; done'
ssh um790pro 'curl -q --noproxy "*" --fail --silent --show-error --max-time 5 http://192.168.1.174:8080/health'
ssh um790pro 'curl -q --noproxy "*" --fail --silent --show-error --max-time 5 http://192.168.1.144:8080/health'
```

Expected: SSH is open on both Macs. Port `8080` succeeds only when the corresponding llama server is running; a stopped application is not a routing failure.

- [ ] **Step 4: Capture Tailscale and firewall state**

```bash
ssh um790pro 'tailscale version; tailscale debug prefs | jq "{AdvertiseRoutes,RouteAll,NoSNAT,NetfilterMode}"; sysctl net.ipv4.ip_forward net.ipv6.conf.all.forwarding; systemctl is-active ufw firewalld'
tailscale debug prefs | jq '{RouteAll,AdvertiseRoutes,NoSNAT,NetfilterMode}'
```

Expected baseline:

- `um790pro`: no advertised routes, `RouteAll = false`, `NoSNAT = false`, netfilter
  mode enabled, IPv4 forwarding enabled, IPv6 forwarding disabled (`0`), UFW active.
- `zenbook`: `RouteAll = false`.

Stop and investigate if IPv6 forwarding is already `1`; the IPv4-only helper must not
silently preserve an unexpected router role.

- [ ] **Step 5: Align the Tailscale CLI and daemon before mutating routes**

The observed CachyOS client was `1.102.2` while the daemon was `1.98.10`. Arrange a LAN fallback path to `um790pro`, then ask the user to run locally on it:

```bash
sudo systemctl restart tailscaled
tailscale version
tailscale ping zenbook
```

Expected: client and daemon versions agree, and `zenbook` remains reachable. If they do
not agree, inspect the installed package, service executable, and live process before
continuing:

```bash
pacman -Q tailscale
systemctl cat tailscaled
main_pid="$(systemctl show --property MainPID --value tailscaled)"
readlink -f "/proc/${main_pid}/exe"
```

If the installed package or service path is stale, stop and ask the user to perform
their normal full CachyOS system upgrade (`sudo pacman -Syu`) from a recoverable local
session before restarting `tailscaled`. Do not recommend a package-only partial upgrade.
Stop if multiple installations or a custom service path remain unresolved. Do not
proceed if restarting `tailscaled` removes remote access and there is no LAN fallback.

### Task 2: Add the `m1max` router canary to NixOS and CachyOS management

**Files:**

- Modify: `hosts/um790pro/nixos/configuration.nix`
- Modify: `install.sh`

- [ ] **Step 1: Declare the NixOS subnet-router role**

Add a host-specific Tailscale block to `hosts/um790pro/nixos/configuration.nix`:

```nix
services.tailscale = {
  useRoutingFeatures = "server";
  openFirewall = true;
  extraSetFlags = [
    "--accept-routes=false"
    "--advertise-routes=192.168.1.174/32"
    "--snat-subnet-routes=true"
  ];
};

# Only IPv4 host routes are advertised; keep IPv6 host behavior unchanged.
boot.kernel.sysctl."net.ipv6.conf.all.forwarding" = lib.mkForce false;
```

The list merges with the common `--hostname=um790pro` setting. Keep the canary limited to `m1max`; `m3max` is added only after LTE verification.

- [ ] **Step 2: Add an idempotent CachyOS helper**

Add `configure_tailscale_subnet_router` near `enable_tailscale_service` in `install.sh`. It must:

1. Return without changes unless `HOSTNAME_SHORT == um790pro`.
2. Check for an active/authenticated `tailscaled`. Fail clearly in focused/strict mode;
   log the login-and-rerun instruction and skip successfully in full-install mode.
3. Require `net.ipv6.conf.all.forwarding = 0` before mutation and fail without changing
   state if it is enabled unexpectedly.
4. Write `/etc/sysctl.d/99-tailscale-subnet-router.conf` with only
   `net.ipv4.ip_forward = 1`. Do not enable global IPv6 forwarding for these IPv4-only
   routes; doing so can change router-advertisement handling.
5. Load only that sysctl file, not every unrelated sysctl file.
6. Run:

```bash
sudo tailscale set \
  --accept-routes=false \
  --advertise-routes=192.168.1.174/32 \
  --snat-subnet-routes=true
```

Do not add broad UFW forwarding rules. Tailscale's enabled netfilter mode should enforce tailnet policy; diagnose packet counters before adding any narrow `ufw route` exception.

- [ ] **Step 3: Expose a focused installer action**

Extend `main()` so this applies only the relevant setup:

```bash
./install.sh tailscale-subnet-router
```

The action installs/enables Tailscale if needed, then calls
`configure_tailscale_subnet_router` in strict mode. Strict mode must fail if the daemon
is not authenticated. Determine this exactly with:

```bash
tailscale status --json --peers=false | jq -r '.BackendState'
```

Do not apply sysctl or route preferences until the result is `Running`. For any other
state, print these recovery commands:

```bash
sudo tailscale up
./install.sh tailscale-subnet-router
```

Also call the function from the normal
full install after `enable_tailscale_service`, but in best-effort mode: if this is a fresh
machine that has not joined the tailnet yet, print the exact login-and-rerun instruction
and return successfully rather than breaking the full installation. Once authenticated,
rerunning either action must converge to the declared route settings.

- [ ] **Step 4: Validate without activating anything**

```bash
bash -n install.sh
nixfmt --check hosts/um790pro/nixos/configuration.nix
nix eval --raw .#nixosConfigurations.um790pro.config.services.tailscale.useRoutingFeatures
nix eval --json .#nixosConfigurations.um790pro.config.services.tailscale.openFirewall
nix eval --json .#nixosConfigurations.um790pro.config.services.tailscale.extraSetFlags
git diff --check -- install.sh hosts/um790pro/nixos/configuration.nix
```

Expected: `server`, `true`, and a flag list containing the hostname, canary `/32`, explicit SNAT, and `accept-routes=false`.

Also evaluate the IPv6 override and expect `false`:

```bash
nix eval --json '.#nixosConfigurations.um790pro.config.boot.kernel.sysctl."net.ipv4.conf.all.forwarding"'
nix eval --json '.#nixosConfigurations.um790pro.config.boot.kernel.sysctl."net.ipv6.conf.all.forwarding"'
```

Expected: IPv4 is `true`; IPv6 is `false`.

Assert that mutually exclusive route flags occur exactly once:

```bash
nix eval --json .#nixosConfigurations.um790pro.config.services.tailscale.extraSetFlags \
  | jq -e '
      map(select(startswith("--advertise-routes="))) == ["--advertise-routes=192.168.1.174/32"] and
      map(select(startswith("--accept-routes="))) == ["--accept-routes=false"] and
      map(select(startswith("--snat-subnet-routes="))) == ["--snat-subnet-routes=true"]
    '
```

The IPv6 invariant is also exact: CachyOS leaves the observed false value unchanged,
and NixOS force-disables it. Both managed paths must finish with IPv6 forwarding off.

Do not run `nixos-rebuild`; the active machine is CachyOS, and repository rules require the user to run any future NixOS rebuild.

### Task 3: Make `zenbook` the first Linux route consumer

**Files:**

- Modify: `hosts/zenbook/nixos/configuration.nix`

- [ ] **Step 1: Declare client routing behavior**

Add:

```nix
services.tailscale = {
  useRoutingFeatures = "client";
  extraSetFlags = [ "--accept-routes=true" ];
};
```

This merges with the shared hostname flag and the VLESS-owned `--accept-dns=false`. Do not enable Tailscale DNS or change sing-box routing in this task.

- [ ] **Step 2: Evaluate the exact result**

```bash
nixfmt --check hosts/zenbook/nixos/configuration.nix
nix eval --raw .#nixosConfigurations.zenbook.config.services.tailscale.useRoutingFeatures
nix eval --json .#nixosConfigurations.zenbook.config.services.tailscale.extraSetFlags
git diff --check -- hosts/zenbook/nixos/configuration.nix
```

Expected: `client`; flags contain `--hostname=zenbook` and `--accept-routes=true`. `--accept-dns=false` remains in `extraUpFlags` and is unchanged.

Assert that there is exactly one route-acceptance flag:

```bash
nix eval --json .#nixosConfigurations.zenbook.config.services.tailscale.extraSetFlags \
  | jq -e 'map(select(startswith("--accept-routes="))) == ["--accept-routes=true"]'
```

- [ ] **Step 3: Ask the user to apply the `zenbook` configuration**

The implementation agent must not run this command. Ask the user to execute:

```bash
sudo nixos-rebuild switch --flake .#zenbook
```

Then verify read-only:

```bash
tailscale debug prefs | jq '{RouteAll,AdvertiseRoutes}'
```

Expected before route approval: `RouteAll = true`; the Mac route might not yet appear.

### Task 4: Add tailnet access policy without broadening subnet sources

**Files:** None in this repository; edit the existing tailnet policy in the Tailscale admin console.

- [ ] **Step 1: Back up the existing policy**

Copy the current HuJSON policy to a local secure scratch file outside git. Never replace the whole policy with the snippets below and never commit login identifiers or unrelated policy content.

- [ ] **Step 2: Add stable policy aliases**

Merge into the existing `hosts` section:

```jsonc
"hosts": {
  "m1max-lan": "192.168.1.174",
  "m3max-lan": "192.168.1.144"
}
```

- [ ] **Step 3: Grant all real Tailscale devices all IP access to the two Macs**

Merge this grant with the existing `grants` array:

```jsonc
{
  "src": [
    "autogroup:member",
    "autogroup:tagged",
    "autogroup:shared"
  ],
  "dst": ["m1max-lan"],
  "ip": ["*"]
}
```

For the canary this implements the explicit decision to allow all ports and IP
protocols from all member-owned, tagged, and shared Tailscale devices to `m1max` only.
Task 7 extends the same grant to `m3max` after the mandatory stop-point. Do not simplify
the source to `"*"`: in Tailscale policy that also includes sources behind other
approved subnet routes.

This grant does not disable the macOS firewall and does not make stopped services listen. It only permits routed tailnet packets to reach the destination IPs.

- [ ] **Step 4: Validate and save the policy**

First confirm the existing tailnet policy accepts Grants and the
`autogroup:shared` source selector. Use the admin editor's validation/preview before
saving. If the selector is rejected, stop and resolve the policy-version/schema issue;
do not replace it with `"*"`. Confirm existing grants, ACLs, SSH rules, tags, tests,
and auto-approvers remain intact. Do not add `autoApprovers` or retag `um790pro`
during the canary; approve routes manually.

### Task 5: Activate and approve only the `m1max` route

**Files:** Runtime and Tailscale admin state only.

- [ ] **Step 1: Apply the CachyOS router helper from a recoverable session**

Ask the user to run on `um790pro`, preferably from its LAN console/session:

```bash
cd /home/nik/nix-config
./install.sh tailscale-subnet-router
tailscale debug prefs | jq '{AdvertiseRoutes,RouteAll,NoSNAT,NetfilterMode}'
sysctl net.ipv4.ip_forward net.ipv6.conf.all.forwarding
```

Expected:

- advertised routes contain only `192.168.1.174/32`;
- `RouteAll = false` on the router;
- `NoSNAT = false`;
- IPv4 forwarding is enabled; IPv6 forwarding is exactly `0`.

- [ ] **Step 2: Approve the route manually**

In Tailscale Admin → Machines → `um790pro` → Subnets, enable only `192.168.1.174/32`.

- [ ] **Step 3: Verify route injection on `zenbook`**

```bash
ip route show table 52 2>/dev/null | rg '192\.168\.1\.174' || true
ip route get 192.168.1.174
tailscale status
```

Expected on the current Linux client/version: table 52 contains the `/32`; the supported
behavioral check is that the full route lookup selects the Tailscale path. Treat table
number `52` as a diagnostic implementation detail rather than a stable API. If the route
is absent, check route approval and `RouteAll` before touching firewalls.

- [ ] **Step 4: Verify from the current network**

```bash
ping -c 3 192.168.1.174
ssh -F /dev/null -i ~/.ssh/id_rsa_1 -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new nik@192.168.1.174 hostname
curl -q --noproxy '*' --fail --silent --show-error --max-time 10 http://192.168.1.174:8080/health
```

Expected: ping and SSH succeed; the health endpoint succeeds when llama-server is
running. `-F /dev/null` excludes both `ProxyJump` and any independent `ProxyCommand`;
`curl -q --noproxy '*'` excludes `.curlrc` and explicit proxy environment settings.

- [ ] **Step 5: Diagnose forwarding in layers if the route exists but traffic fails**

Check in order:

1. `ssh um790pro 'ping -c 1 192.168.1.174'` and direct service access from `um790pro`.
2. Tailnet policy preview for the actual source device and `m1max-lan`.
3. `tailscale debug prefs` for `NoSNAT = false` and netfilter enabled.
4. With user-provided sudo, packet counters or `tcpdump` on `tailscale0` and the
   LAN interface recorded in Task 1.
5. UFW routed-packet logs/counters.

Before any firewall mutation, re-run `ip route get 192.168.1.174` and confirm it still
selects the recorded LAN interface. Only if counters prove UFW drops an otherwise
policy-approved flow should the implementation add a narrowly scoped, reproducible
`tailscale0 -> $UM_LAN_IF -> 192.168.1.174/32` rule to `install.sh`. The helper must
discover and validate `$UM_LAN_IF` at runtime rather than persist a hardcoded interface.
Never set global forwarding to allow.

### Task 6: Perform the mandatory LTE canary and rollback drill

**Files:** Runtime only.

- [ ] **Step 1: Remove the local-LAN shortcut**

Connect `zenbook` through LTE or phone tethering and verify it no longer has a connected route to the home LAN:

```bash
ip -4 route
ip route get 192.168.1.174
```

Expected: no local `192.168.1.0/24` path; the `/32` remains injected by Tailscale.

- [ ] **Step 2: Test Tailscale, ICMP, SSH, and a second service**

```bash
tailscale ping um790pro
ping -c 3 192.168.1.174
ssh -F /dev/null -i ~/.ssh/id_rsa_1 -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new nik@192.168.1.174 hostname
curl -q --noproxy '*' --fail --silent --show-error --max-time 10 http://192.168.1.174:8080/health
```

Expected: Tailscale reaches `um790pro`; direct IP access reaches `m1max`; SSH reports
`m1max`; port `8080` works when the service is running. `curl -q` ignores `.curlrc`,
and `--noproxy '*'` ignores explicit proxy environment settings. These are representative
reachability checks, not an exhaustive test of 65,535 ports or every IP protocol; the
all-protocol scope is established by the validated `ip: ["*"]` grant.

- [ ] **Step 3: Verify a temporary UDP flow**

With the user present at `m1max`, start a one-shot unprivileged UDP listener:

```bash
nc -u -l 19099
```

First send a token from `um790pro` over the ordinary LAN; this separates macOS
listener/firewall behavior from Tailscale routing:

```bash
printf 'lan-udp-baseline\n' | nc -u -w 2 192.168.1.174 19099
```

Restart the one-shot listener, then send a unique token from `zenbook` over LTE:

```bash
printf 'tailscale-udp-canary\n' | nc -u -w 2 192.168.1.174 19099
```

Expected: the token appears on `m1max`. Stop the temporary listener immediately. If
the installed BSD/netcat variant uses different listen syntax, consult `nc -h` and
adjust only the local invocation; do not add a persistent service or firewall opening.

During the LTE ICMP/SSH/HTTP/UDP checks, capture the unique test traffic on
`um790pro` with user-provided sudo on both `tailscale0` and the LAN interface recorded
in Task 1. The evidence must show ingress on `tailscale0` and matching egress on the
discovered LAN interface; do not hardcode `wlan0`.

- [ ] **Step 4: Verify unrelated routing still works**

```bash
systemctl is-active tailscaled vless-sing-box
tailscale ping london
curl --fail --silent --show-error --max-time 10 https://example.com/ >/dev/null
```

Expected: both local services are active, London remains reachable over Tailscale, and ordinary internet access still works through the existing policy. Do not change or restart London.

- [ ] **Step 5: Execute the rollback drill**

Before adding `m3max`, actually withdraw and restore the canary once, without using
`tailscale down`:

```bash
# On um790pro, withdraw all canary routes:
sudo tailscale set --advertise-routes=

# On a Linux client, only if it should stop accepting every subnet route:
sudo tailscale set --accept-routes=false
```

Also disable the route in the admin console. The canary configuration intentionally
still declares the route, so a later installer/Nix activation would restore it. After
the drill, re-run `./install.sh tailscale-subnet-router`, restore
`--accept-routes=true` on `zenbook`, re-approve the route, and repeat SSH once. For a
permanent rollback, revert the declarations before running either activation path.

Stop here and report results before expanding the route set.

### Task 7: Expand the implementation to `m3max`

**Files:**

- Modify: `hosts/um790pro/nixos/configuration.nix`
- Modify: `hosts/m3max/nixos/configuration.nix`
- Modify: `install.sh`

- [ ] **Step 1: Add the second route in both managed router paths**

Change the advertisement in the NixOS config and CachyOS helper to exactly:

```text
192.168.1.174/32,192.168.1.144/32
```

Keep SNAT enabled and `accept-routes=false` on `um790pro`.

- [ ] **Step 2: Make the observed `m3max` SSH state declarative**

Add to `hosts/m3max/nixos/configuration.nix`:

```nix
# Allow SSH access from the local network, including through the Tailscale subnet router.
services.openssh.enable = true;
```

This matches the already-running Remote Login service and the `m1max` configuration; it does not open every macOS service automatically.

- [ ] **Step 3: Re-run static validation**

```bash
bash -n install.sh
nixfmt --check hosts/um790pro/nixos/configuration.nix hosts/m3max/nixos/configuration.nix
nix eval --json .#nixosConfigurations.um790pro.config.services.tailscale.extraSetFlags
nix eval --json .#darwinConfigurations.m3max.config.services.openssh.enable
git diff --check -- install.sh hosts/um790pro/nixos/configuration.nix hosts/m3max/nixos/configuration.nix
```

Expected: the router advertises exactly two `/32`s and `m3max` OpenSSH evaluates to `true`.

Assert that the final router has exactly one effective value for each routing flag:

```bash
nix eval --json .#nixosConfigurations.um790pro.config.services.tailscale.extraSetFlags \
  | jq -e '
      map(select(startswith("--advertise-routes="))) == ["--advertise-routes=192.168.1.174/32,192.168.1.144/32"] and
      map(select(startswith("--accept-routes="))) == ["--accept-routes=false"] and
      map(select(startswith("--snat-subnet-routes="))) == ["--snat-subnet-routes=true"]
    '
```

- [ ] **Step 4: Ask the user to apply both sides**

On active CachyOS `um790pro`:

```bash
./install.sh tailscale-subnet-router
```

For the Mac declaration, ask the user to run:

```bash
darwin-rebuild switch --flake .#m3max
```

Do not run the Darwin rebuild on the user's behalf. Run the CachyOS helper only after
the user explicitly starts the activation phase and a recoverable session is available.

- [ ] **Step 5: Extend the policy grant to `m3max`**

In the validated existing grant, change only the destination list:

```jsonc
"dst": ["m1max-lan", "m3max-lan"]
```

Validate/save the tailnet policy before route approval. Confirm there was no previously
approved broader route covering `192.168.1.144`; the `/32` added here must be the only
route that newly makes this address reachable.

- [ ] **Step 6: Approve and verify the new route**

Enable `192.168.1.144/32` in the Tailscale admin console. From `zenbook` over LTE:

```bash
ip route show table 52 2>/dev/null | rg '192\.168\.1\.(174|144)' || true
ping -c 3 192.168.1.144
ssh -F /dev/null -i ~/.ssh/id_rsa_1 -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new nik@192.168.1.144 hostname
curl -q --noproxy '*' --fail --silent --show-error --max-time 10 http://192.168.1.144:8080/health
```

Expected: both `/32`s are present; SSH reports `m3max`; the health endpoint works when its llama stack is running.

### Task 8: Enroll all remaining Tailscale clients safely

**Files:**

- Modify: `hosts/x1carbon/nixos/configuration.nix`
- Runtime preferences on other Linux tailnet devices

- [ ] **Step 1: Refresh the device inventory**

```bash
tailscale status --json \
  | jq -r '([.Self] + ((.Peer // {}) | to_entries | map(.value)))[] | [.HostName, .OS, (.Online|tostring), (.TailscaleIPs[0] // "")] | @tsv' \
  | sort
```

Classify each device as:

- macOS, Windows, iOS, or Android: subnet routes are normally accepted by default;
- Linux client: needs `--accept-routes=true`;
- `um790pro`: router, must remain `--accept-routes=false`.

- [ ] **Step 2: Make the managed `x1carbon` client declarative**

Add the same client settings used by `zenbook`:

```nix
services.tailscale = {
  useRoutingFeatures = "client";
  extraSetFlags = [ "--accept-routes=true" ];
};
```

Validate:

```bash
nixfmt --check hosts/x1carbon/nixos/configuration.nix
nix eval --raw .#nixosConfigurations.x1carbon.config.services.tailscale.useRoutingFeatures
nix eval --json .#nixosConfigurations.x1carbon.config.services.tailscale.extraSetFlags
```

Assert that `x1carbon` has exactly one effective acceptance flag:

```bash
nix eval --json .#nixosConfigurations.x1carbon.config.services.tailscale.extraSetFlags \
  | jq -e 'map(select(startswith("--accept-routes="))) == ["--accept-routes=true"]'
```

Ask the user to run the `x1carbon` NixOS rebuild. Never run it on the user's behalf.

- [ ] **Step 3: Enroll non-Nix Linux clients one at a time**

For each Linux device outside this flake, first check for a conflicting local route:

```bash
ip -4 addr
ip route get 192.168.1.174
ip route get 192.168.1.144
tailscale debug prefs | jq '{RouteAll,AdvertiseRoutes}'
```

If neither destination is a real local device on that host's current network, enable routes:

```bash
sudo tailscale set --accept-routes=true
```

Then test both IPs. Current Linux peers include `rpi4`, London, `zmops`, and `zmops-backup`; refresh the inventory rather than treating this list as permanent. On London, change only the Tailscale preference after the route-conflict audit, do not edit or restart microsocks, Tailscale Serve, Caddy, or the proxy bundle, and re-verify the existing London service afterward.

- [ ] **Step 4: Verify every currently online non-router device**

Before connecting, inspect that client's current LAN routes for both exact addresses
(for example, `route -n get 192.168.1.174` and `route -n get 192.168.1.144` on
macOS, or `Get-NetRoute` on Windows). From every currently online macOS, Windows, iOS,
or Android Tailscale device without a collision, connect to a known service by IP. No
DNS test is required. Record any client where subnet route acceptance was manually
disabled and restore it through that platform's Tailscale UI.

The same completion rule applies to online Linux devices from Step 3: inspect route
acceptance and perform a direct-IP test on every online device except `um790pro`.
List offline, inaccessible, or colliding devices explicitly as `pending`; do not claim
the all-device rollout complete while any current device is untested.

### Task 9: Verify persistence and failure behavior

**Files:** Runtime only.

- [ ] **Step 1: Verify Tailscale preference persistence**

With a LAN fallback available, ask the user to restart `tailscaled` on `um790pro` and verify:

```bash
tailscale debug prefs | jq '{AdvertiseRoutes,RouteAll,NoSNAT}'
```

Expected: both `/32`s remain advertised, the router still rejects accepted routes, and SNAT remains enabled.

- [ ] **Step 2: Verify endpoint absence fails closed**

Disconnect or sleep one Mac while leaving `um790pro` online, then connect to its IP from a tailnet client.

Expected: the connection times out; the advertised route remains present and traffic does not fall through to another network. Restore the Mac and verify access returns without changing Tailscale state.

- [ ] **Step 3: Check address-collision behavior**

On a client attached to a foreign `192.168.1.0/24` network, inspect both `/32` lookups before connecting. Document that these exact IPs are intentionally claimed by the tailnet routes. If a real collision is encountered, stop and design 4via6 or a dedicated rare-prefix VLAN; do not broaden or dynamically rewrite routes in this implementation.

### Task 10: Document operations and perform final validation

**Files:**

- Modify: `docs/proxy-setup.md`

- [ ] **Step 1: Document the final topology**

Add a subnet-router section covering:

- `um790pro` as the route owner;
- both `/32` addresses and DHCP reservation requirement;
- default SNAT and the current `um790pro` LAN source visible to the Macs (observed as
  `192.168.1.241` during design);
- all-device/all-protocol tailnet grant semantics;
- Linux `accept-routes` requirement;
- IP-only access and the fact that MagicDNS does not name LAN-only Macs;
- expected timeout when a Mac is asleep or absent;
- the CachyOS helper and NixOS equivalents.

- [ ] **Step 2: Add the operational rollback**

Document this order:

1. Withdraw routes on `um790pro` with `tailscale set --advertise-routes=`.
2. Disable both routes in the admin console.
3. Remove or disable the dedicated grant if access must be revoked.
4. Revert route advertisements in both `install.sh` and the NixOS host config.
5. Leave Tailscale itself online so `um790pro` remains reachable.
6. Disable `accept-routes` on a client only if it should stop consuming every tailnet subnet route. Never use London as the rollback-drill client; its only permitted mutation in this plan is the audited one-time route-acceptance setting, followed by health checks without service restarts.

- [ ] **Step 3: Run repository checks**

```bash
bash -n install.sh
nixfmt --check \
  hosts/um790pro/nixos/configuration.nix \
  hosts/zenbook/nixos/configuration.nix \
  hosts/x1carbon/nixos/configuration.nix \
  hosts/m3max/nixos/configuration.nix
nix eval --raw .#nixosConfigurations.um790pro.config.services.tailscale.useRoutingFeatures
nix eval --json .#nixosConfigurations.um790pro.config.services.tailscale.extraSetFlags
nix eval --json '.#nixosConfigurations.um790pro.config.boot.kernel.sysctl."net.ipv4.conf.all.forwarding"'
nix eval --json '.#nixosConfigurations.um790pro.config.boot.kernel.sysctl."net.ipv6.conf.all.forwarding"'
nix eval --raw .#nixosConfigurations.zenbook.config.services.tailscale.useRoutingFeatures
nix eval --json .#nixosConfigurations.zenbook.config.services.tailscale.extraSetFlags
nix eval --raw .#nixosConfigurations.x1carbon.config.services.tailscale.useRoutingFeatures
nix eval --json .#darwinConfigurations.m3max.config.services.openssh.enable
git diff --check
git status --short
```

Expected: shell/Nix formatting passes; the router has exactly two `/32`s with SNAT and no route acceptance; managed clients accept routes; `m3max` SSH is declarative; only intended files are changed.

- [ ] **Step 4: Report runtime evidence separately from static checks**

The completion report must include:

- successful LTE access to both IPs with SSH config disabled via `-F /dev/null`;
- representative ICMP, SSH, and port `8080` results;
- Tailscale route approval state;
- `AdvertiseRoutes`, `RouteAll`, and `NoSNAT` values on the router;
- direct-IP and route-acceptance results for every currently online non-router device;
- an explicit pending list for every offline, inaccessible, or colliding device;
- confirmation that VLESS and London reachability were not disturbed;
- any client skipped because of an address collision.

Do not commit unless the user separately requests commits.
