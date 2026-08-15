#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
script="$repo_root/modules/home-manager/scripts/handle-monitor-connect"
tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

calls="$tmp_dir/hyprctl.calls"

cat > "$tmp_dir/hyprctl" <<'MOCK'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$HYPRCTL_CALLS"

# One missing workspace must not stop the long-running event handler.
[[ "${*: -1}" != "3 DP-1" ]]
MOCK
chmod +x "$tmp_dir/hyprctl"

export HYPRCTL_BIN="$tmp_dir/hyprctl"
export HYPRCTL_CALLS="$calls"

# shellcheck source=../modules/home-manager/scripts/handle-monitor-connect
source "$script"

handle_monitor_event 'monitoraddedv2>>2,DP-1,Huawei Technologies Co. Inc. MateView'
handle_monitor_event 'monitorremovedv2>>2,DP-1,Huawei Technologies Co. Inc. MateView'

cat > "$tmp_dir/expected" <<'EXPECTED'
dispatch moveworkspacetomonitor 1 DP-1
dispatch moveworkspacetomonitor 2 DP-1
dispatch moveworkspacetomonitor 3 DP-1
dispatch moveworkspacetomonitor 4 DP-1
dispatch moveworkspacetomonitor 5 DP-1
EXPECTED

diff -u "$tmp_dir/expected" "$calls"

: > "$calls"
handle_monitor_event 'monitoradded>>HDMI-A-1'

for workspace in 1 2 3 4 5; do
  expected="dispatch moveworkspacetomonitor $workspace HDMI-A-1"
  if ! grep -Fxq "$expected" "$calls"; then
    printf 'Missing legacy monitor event call: %s\n' "$expected" >&2
    exit 1
  fi
done

printf 'PASS: monitor hotplug uses the event monitor name and survives a missing workspace\n'
