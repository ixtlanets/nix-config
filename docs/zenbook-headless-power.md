# Zenbook headless power behavior

## Current status

As of 2026-09-17, the Zenbook can run as a headless host with its lid closed,
but it cannot reliably wake itself from `s2idle`. The experimental
`zenbook-battery-guard.service` is therefore disabled and must remain disabled.

The active policy is:

- Lid-close events are ignored on battery, external power, and while docked.
- Removing AC does not intentionally suspend the host at 30% battery.
- UPower requests a final power-off at 2% while userspace is running.
- Reconnecting USB-C power is not expected to wake a suspended or powered-off
  host.

The relevant managed files are:

- `dotfiles/omarchy/system/logind.conf.d/90-headless-lid.conf`
- `dotfiles/omarchy/system/UPower.conf.d/90-headless-battery.conf`
- `scripts/omarchy-apply-system.sh`

The live machine still has the experimental unit and helper at
`/etc/systemd/system/zenbook-battery-guard.service` and
`/usr/local/libexec/zenbook-battery-guard`, but the unit is both `disabled` and
`inactive`. Omarchy provisioning explicitly disables it and does not install a
replacement.

## What was attempted

The intended behavior was to keep the host online during short power outages,
then suspend at 30% battery and periodically wake every two minutes to detect
restored AC power.

The following work was completed:

1. Updated the BIOS to `UX3404VC.305`.
2. Configured logind to ignore all lid-close events.
3. Configured UPower percentage thresholds at 35% low, 32% critical, and 2%
   action, with `CriticalPowerAction=PowerOff`.
4. Built a root systemd guard that polled `BAT0` and `ADP1`, suspended at 30%,
   and attempted periodic wakeups.
5. Tested direct RTC alarms through `rtcwake`.
6. Replaced direct RTC alarms with transient systemd timers using
   `WakeSystem=yes`.
7. Corrected an implementation bug by changing `systemctl suspend` to
   `systemctl --wait suspend`. Without `--wait`, the command returned as soon as
   suspend was queued and the guard removed its wake timer before entering
   sleep.

## Verified results

Lid handling works. During the physical test, the journal recorded `Lid closed`
at 15:54:44 and `Lid opened` at 15:55:20. SSH, `sshd`, the user manager, and the
tmux session remained available throughout.

Resume networking also works after a manual wake. NetworkManager generally
restored Wi-Fi within a few seconds, followed by Tailscale.

Automatic wake does not work reliably:

- USB-C power insertion did not wake the host from `s2idle`.
- A direct RTC test entered suspend at 16:40:37 and exited at 16:44:55 only
  after keyboard input, rather than at the requested 120-second alarm.
- The first integrated systemd timer test revealed the missing `--wait`: the
  timer was stopped immediately before actual suspend.
- After adding `systemctl --wait suspend`, the final integrated test still
  resumed only after keyboard input.

The system exposes both `rtc0` (`rtc_cmos`) and `rtc1` (`acpi-tad`, ACPI device
`AWAC`). Both report wake capability, and `AWAC` is enabled in
`/proc/acpi/wakeup`, but the tests did not establish a timer mechanism that can
reliably wake this firmware from `s2idle`.

## Outage behavior

With the guard disabled, disconnecting power leaves the machine running and
reachable while battery capacity remains. Crossing 30% has no special effect.
If userspace remains active down to 2%, UPower should request a clean power-off.

There is no automatic recovery guarantee after that power-off. Connecting USB-C
power may charge the battery, but a physical power-button press and LUKS unlock
may still be required. Avoid relying on this host for unattended availability
until wake-on-AC or a reliable timed wake has been demonstrated.

If the experimental guard is ever enabled manually, it will suspend at 30% and
can leave the machine unreachable indefinitely. UPower cannot enforce its 2%
action while userspace is frozen in suspend.

## Operational notes

Do not restart `systemd-logind` merely to apply the lid configuration. A prior
restart terminated the graphical session and its tmux session; apply this
setting at reboot instead.

Useful status checks are:

```bash
systemctl is-enabled zenbook-battery-guard.service
systemctl is-active zenbook-battery-guard.service
cat /sys/class/power_supply/BAT0/capacity
cat /sys/class/power_supply/ADP1/online
```

The expected guard results are `disabled` and `inactive`.

## Possible future investigation

No further wake diagnosis was requested in this session. If it is resumed,
test one variable at a time and keep physical keyboard access available:

1. Test `/dev/rtc1` (`acpi-tad`) directly instead of the default `/dev/rtc0`.
2. Check firmware options for wake on AC or restore after AC loss.
3. Compare `s2idle` with `deep`, accounting for driver and resume risks.
4. Consider an external UPS or remotely controllable hardware power solution
   if unattended recovery is required.
