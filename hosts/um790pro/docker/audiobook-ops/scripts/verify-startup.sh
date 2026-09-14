#!/usr/bin/env bash

set -u

failures=0
pass() { echo "PASS  $1"; }
fail() { echo "FAIL  $1"; failures=$((failures + 1)); }

units=(
  audiobook-ops-compose.service
  audiobook-ops-policy.timer
  audiobook-ops-worker.timer
  audiobook-ops-publisher.timer
  audiobook-ops-cleanup.timer
  audiobook-ops-backup.timer
  audiobook-ops-healthcheck.timer
)
for unit in "${units[@]}"; do
  if systemctl is-enabled --quiet "$unit"; then
    pass "enabled after boot: $unit"
  else
    fail "enabled after boot: $unit"
  fi
  if systemctl is-active --quiet "$unit"; then
    pass "active after boot: $unit"
  else
    fail "active after boot: $unit"
  fi
  if [[ $unit == *.timer ]]; then
    next_realtime=$(systemctl show "$unit" --property=NextElapseUSecRealtime --value 2>/dev/null || true)
    next_monotonic=$(systemctl show "$unit" --property=NextElapseUSecMonotonic --value 2>/dev/null || true)
    if [[ ( -n $next_realtime && $next_realtime != infinity ) || ( -n $next_monotonic && $next_monotonic != infinity ) ]]; then
      pass "next trigger after boot: $unit"
    else
      fail "next trigger after boot: $unit"
    fi
  fi
done

for container in \
  audiobook-ops \
  audiobook-ops-flaresolverr \
  audiobook-ops-rutracker-gateway \
  audiobook-ops-prowlarr \
  audiobook-ops-transmission; do
  state=$(docker inspect --format '{{.State.Running}}|{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$container" 2>/dev/null || true)
  if [[ $state == true\| || $state == true\|healthy ]]; then
    pass "container after boot: $container"
  else
    fail "container after boot: $container"
  fi
done

if ((failures)); then
  echo "Startup verification failed: $failures check(s)"
  exit 1
fi
echo "Startup verification passed"
