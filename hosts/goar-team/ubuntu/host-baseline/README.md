# goar-team host baseline

Ubuntu resource safeguards adapted from the London baseline: persistent 2 GiB
`/swapfile` and disabled/masked `fwupd-refresh.timer`. Manual firmware commands
remain available. Existing services are not restarted by this baseline.

```sh
REMOTE=root@<IP> SSH_KEY="$HOME/.ssh/id_rsa_1" \
  hosts/goar-team/ubuntu/host-baseline/apply.sh
```

`REMOTE` is required (no live default); `SSH_KEY` is optional. The root session
needs `sudo` and the standard Ubuntu util-linux/systemd tools. `SWAP_FILE`
(default `/swapfile`) and `SWAP_SIZE_MIB` (default `2048`) can be overridden.
The inherited baseline creates swap atomically, enforces `root:root 0600`, and
refuses symlinks, non-swap files, mismatched sizes and duplicate/conflicting
fstab entries. Repeated application keeps the existing swap.

Verify on the new VPS:

```sh
ssh root@<IP> 'systemctl is-enabled fwupd-refresh.timer; systemctl is-active fwupd-refresh.timer; swapon --show; free -h'
```

Expect `masked`, `inactive`, active 2 GiB swap, and one canonical
`/swapfile none swap sw 0 0` entry in `/etc/fstab`.
The firewall is a separate operator step in the [runbook](../../../../docs/goar-team-vless-node.md).

Rollback deliberately: unmask and enable the timer with `systemctl unmask
fwupd-refresh.timer` and `systemctl enable --now fwupd-refresh.timer`. To remove
swap, remove its fstab entry first, then `swapoff /swapfile`; keep it enabled
unless the resource policy changes.
