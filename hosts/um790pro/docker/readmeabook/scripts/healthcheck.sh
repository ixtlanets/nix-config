#!/usr/bin/env bash

set -euo pipefail

bundle_dir=${READMABOOK_BUNDLE_DIR:-/home/nik/.local/share/nix-config-services/readmeabook}
publisher_config=${READMABOOK_PUBLISHER_CONFIG:-/home/nik/.config/readmeabook/publisher.json}
policy_config=${READMABOOK_TORRENT_POLICY_CONFIG:-/home/nik/.config/readmeabook/torrent-policy.json}
python_bin=${READMABOOK_PYTHON_BIN:-/usr/bin/python3}
docker_bin=${READMABOOK_DOCKER_BIN:-/usr/bin/docker}
health_retries=${READMABOOK_HEALTH_RETRIES:-15}
health_retry_delay_seconds=${READMABOOK_HEALTH_RETRY_DELAY_SECONDS:-3}

check_container() {
  local container=$1
  local attempt state running health

  for ((attempt = 1; attempt <= health_retries; attempt++)); do
    if state=$(
      "$docker_bin" inspect \
        --format '{{.State.Running}}|{{if .State.Health}}{{.State.Health.Status}}{{end}}' \
        "$container"
    ); then
      running=${state%%|*}
      health=${state#*|}
      if [[ $running == true && (-z $health || $health == healthy) ]]; then
        return 0
      fi
    else
      running=false
      health=inspect-failed
    fi

    if ((attempt < health_retries)); then
      sleep "$health_retry_delay_seconds"
    fi
  done

  if [[ $running != true ]]; then
    echo "$container is not running" >&2
  else
    echo "$container health is $health" >&2
  fi
  return 1
}

for container in \
  readmeabook \
  readmeabook-flaresolverr \
  readmeabook-rutracker-gateway \
  readmeabook-prowlarr \
  readmeabook-transmission; do
  check_container "$container"
done

publisher_status=$(
  "$python_bin" "$bundle_dir/scripts/publisher.py" \
    --config "$publisher_config" status --json
)
policy_status=$(
  "$python_bin" "$bundle_dir/scripts/torrent-policy.py" \
    --config "$policy_config" status --json
)
"$python_bin" -c \
  'import json,sys
publisher=json.loads(sys.argv[1])
policy=json.loads(sys.argv[2])
assert not publisher["blocked"], publisher.get("blocked_reason")
assert not policy["capacity_blocked"], "working-set capacity guard is active"
assert policy["active_downloads"] <= 1, "more than one active download"' \
  "$publisher_status" "$policy_status"

echo "ReadMeABook health checks passed"
