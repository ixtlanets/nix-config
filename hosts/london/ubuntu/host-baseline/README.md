# London host baseline

Host-wide resource safeguards for the Ubuntu-managed `london` VPS. This bundle
does not restart or modify microsocks, Tailscale, Docker, Caddy, or Vaultwarden.

It applies two settings:

- creates and enables a persistent 2 GiB `/swapfile`;
- disables and masks `fwupd-refresh.timer` while leaving manual `fwupdmgr`
  operation available.

The swap file protects the 954 MiB VM from abrupt memory exhaustion. Automated
firmware metadata refreshes provide no operational value on this virtual server
and can create avoidable CPU, memory, network, and disk pressure.

## Apply

Run from the repository root:

```sh
hosts/london/ubuntu/host-baseline/apply.sh
```

The script defaults to `ubuntu@london`. The target and swap settings can be
overridden when recovering a replacement host:

```sh
REMOTE=ubuntu@132.145.52.74 \
SWAP_FILE=/swapfile \
SWAP_SIZE_MIB=2048 \
  hosts/london/ubuntu/host-baseline/apply.sh
```

The script is idempotent. It creates a new swap file atomically, enforces
`root:root` ownership and mode `0600`, and refuses to overwrite a non-swap file,
silently resize existing swap, or accept conflicting `/etc/fstab` entries.

## Verify

```sh
ssh ubuntu@london \
  'systemctl is-enabled fwupd-refresh.timer; \
   systemctl is-active fwupd-refresh.timer; \
   swapon --show; \
   free -h'
```

Expected state:

- `fwupd-refresh.timer` is `masked` and `inactive`;
- `/swapfile` is active with a size of 2 GiB;
- `/etc/fstab` contains `/swapfile none swap sw 0 0`.

## Incident history

On 2026-09-15, the VM stopped servicing SSH, Tailscale, and SOCKS traffic at
06:49 UTC. TCP handshakes still completed, but userspace services returned no
data. The final journal sequence started `fwupd-refresh.service`, logged
`fwupdmgr: Updating lvfs`, and then stopped without a clean shutdown, OOM record,
or kernel panic. During diagnosis after reboot, the Oracle VM also showed high
CPU steal under load and had no swap.

The evidence establishes a full VM resource stall, temporally associated with
the firmware refresh. It does not distinguish a guest resource deadlock from
Oracle hypervisor contention, so both safeguards are retained.

## Rollback

Re-enable automatic firmware metadata refreshes:

```sh
ssh ubuntu@london \
  'sudo systemctl unmask fwupd-refresh.timer && \
   sudo systemctl enable --now fwupd-refresh.timer'
```

Removing swap requires deleting its `/etc/fstab` entry before reboot and then
running `sudo swapoff /swapfile`. Keep swap enabled unless the VM size is
increased and the resource policy is deliberately reconsidered.
