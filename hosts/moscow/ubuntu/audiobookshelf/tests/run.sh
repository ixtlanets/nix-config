#!/usr/bin/env bash
set -uo pipefail

TEST_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
BUNDLE_DIR=$(cd -- "$TEST_DIR/.." && pwd)
SCRIPTS_DIR=$BUNDLE_DIR/scripts
FAKES_DIR=$TEST_DIR/fakes

failures=0

run_test() {
  local name=$1

  if "$name"; then
    printf 'ok - %s\n' "$name"
  else
    printf 'not ok - %s\n' "$name" >&2
    failures=$((failures + 1))
  fi
}

cutover_requires_execute() {
  local output status

  output=$(bash "$SCRIPTS_DIR/cutover.sh" 2>&1)
  status=$?

  [[ $status -ne 0 ]] && [[ $output == *"cutover requires --execute"* ]]
}

cutover_requires_rehearsal_id() {
  local output status

  output=$(bash "$SCRIPTS_DIR/cutover.sh" --execute 2>&1)
  status=$?

  [[ $status -ne 0 ]] && [[ $output == *"cutover requires --execute <rehearsal-id>"* ]]
}

rollback_requires_snapshot_id() {
  local output status

  output=$(bash "$SCRIPTS_DIR/rollback.sh" --execute 2>&1)
  status=$?

  [[ $status -ne 0 ]] && [[ $output == *"rollback requires --execute <snapshot-id>"* ]]
}

rollback_rejects_unsafe_snapshot_id() {
  local output status

  output=$(bash "$SCRIPTS_DIR/rollback.sh" --execute ../../etc 2>&1)
  status=$?

  [[ $status -ne 0 ]] && [[ $output == *"invalid snapshot ID"* ]]
}

cleanup_requires_execute() {
  local output status

  output=$(bash "$SCRIPTS_DIR/cleanup.sh" 2>&1)
  status=$?

  [[ $status -ne 0 ]] && [[ $output == *"cleanup requires --execute"* ]]
}

cleanup_requires_cutover_snapshot_id() {
  local output status

  output=$(bash "$SCRIPTS_DIR/cleanup.sh" --execute 2>&1)
  status=$?

  [[ $status -ne 0 ]] && [[ $output == *"cleanup requires --execute <cutover-snapshot-id>"* ]]
}

preflight_propagates_remote_fingerprint_failure() {
  local output status

  output=$(FAKE_SSH_STATUS=1 FAKE_SSH_OUTPUT="fingerprint mismatch: image id" SSH_BIN="$FAKES_DIR/ssh" bash "$SCRIPTS_DIR/preflight.sh" 2>&1)
  status=$?

  [[ $status -ne 0 ]] && [[ $output == *"fingerprint mismatch: image id"* ]]
}

preflight_rejects_changed_image_id() {
  local output status fingerprint

  fingerprint=$'hostname=rpi4\narch=aarch64\nimage_id=sha256:changed\nremote_checks=ok'
  output=$(FAKE_SSH_OUTPUT="$fingerprint" SSH_BIN="$FAKES_DIR/ssh" bash "$SCRIPTS_DIR/preflight.sh" 2>&1)
  status=$?

  [[ $status -ne 0 ]] && [[ $output == *"fingerprint mismatch: image id"* ]]
}

production_compose_preserves_current_topology() {
  local rendered

  rendered=$(docker compose -f "$BUNDLE_DIR/docker-compose.yml" config 2>/dev/null) || return 1

  [[ $rendered == *"nix-config/audiobookshelf:2.36.0-arm64-14a6492c"* ]] &&
    [[ $rendered == *"published: \"13378\""* ]] &&
    [[ $rendered == *"source: /media/disk1/media/meta"* ]] &&
    [[ $rendered == *"target: /config"* ]] &&
    [[ $rendered == *"target: /metadata"* ]] &&
    [[ $rendered == *"target: /audiobooks"* ]] &&
    [[ $rendered != *"read_only: true"* ]]
}

rehearsal_compose_is_private_and_media_read_only() {
  local rendered

  rendered=$(REHEARSAL_STATE_DIR=/tmp/audiobookshelf-rehearsal docker compose -f "$BUNDLE_DIR/docker-compose.rehearsal.yml" config 2>/dev/null) || return 1

  [[ $rendered == *"host_ip: 100.81.67.47"* ]] &&
    [[ $rendered == *"published: \"13379\""* ]] &&
    [[ $rendered == *"source: /tmp/audiobookshelf-rehearsal"* ]] &&
    [[ $rendered == *"target: /config"* ]] &&
    [[ $rendered == *"target: /metadata"* ]] &&
    [[ $rendered == *"target: /audiobooks"* ]] &&
    [[ $rendered == *"read_only: true"* ]]
}

prepare_image_falls_back_to_arm64_transfer() {
  local output status log_file

  log_file=$(mktemp)
  output=$(FAKE_COMMAND_LOG="$log_file" SSH_BIN="$FAKES_DIR/ssh-prepare" DOCKER_BIN="$FAKES_DIR/docker" bash "$SCRIPTS_DIR/prepare-image.sh" 2>&1)
  status=$?

  grep -Fq "docker pull --platform linux/arm64 ghcr.io/advplyr/audiobookshelf:2.36.0" "$log_file" &&
    grep -Fq "ssh docker load" "$log_file" &&
    [[ $status -eq 0 ]] && [[ $output == *"target image prepared"* ]]
}

snapshot_restarts_production_when_copy_fails() {
  local output status log_file source_dir state_dir

  log_file=$(mktemp)
  source_dir=$(mktemp -d)
  state_dir=$(mktemp -d)
  touch "$source_dir/absdatabase.sqlite"

  output=$(
    FAKE_COMMAND_LOG="$log_file" \
      FAKE_TAR_FAIL=1 \
      SSH_BIN="$FAKES_DIR/ssh-exec" \
      SOURCE_STATE_DIR="$source_dir" \
      REMOTE_STATE_DIR="$state_dir" \
      bash "$SCRIPTS_DIR/snapshot.sh" rehearsal 2>&1
  )
  status=$?

  grep -Fq "docker stop --time 30 audiobookshelf" "$log_file" &&
    grep -Fq "docker start audiobookshelf" "$log_file" &&
    [[ $status -ne 0 ]] && [[ $output == *"snapshot failed"* ]]
}

snapshot_creates_verified_copy_and_returns_id() {
  local output status log_file source_dir state_dir snapshot_id

  log_file=$(mktemp)
  source_dir=$(mktemp -d)
  state_dir=$(mktemp -d)
  printf 'database' >"$source_dir/absdatabase.sqlite"
  printf 'metadata' >"$source_dir/item.txt"

  output=$(
    FAKE_COMMAND_LOG="$log_file" \
      SSH_BIN="$FAKES_DIR/ssh-exec" \
      SOURCE_STATE_DIR="$source_dir" \
      REMOTE_STATE_DIR="$state_dir" \
      bash "$SCRIPTS_DIR/snapshot.sh" rehearsal 2>&1
  )
  status=$?
  snapshot_id=$(awk -F= '$1 == "snapshot_id" { print $2; exit }' <<<"$output")

  [[ $status -eq 0 ]] &&
    [[ -n $snapshot_id ]] &&
    [[ -f $state_dir/snapshots/$snapshot_id/state/absdatabase.sqlite ]] &&
    [[ -f $state_dir/snapshots/$snapshot_id/files.sha256 ]] &&
    [[ $(stat -c %a "$state_dir") == 700 ]] &&
    [[ $(stat -c %a "$state_dir/snapshots") == 700 ]] &&
    [[ $(stat -c %a "$state_dir/snapshots/$snapshot_id") == 700 ]] &&
    [[ $(stat -c %a "$state_dir/snapshots/$snapshot_id/state") == 700 ]] &&
    grep -Fq "docker start audiobookshelf" "$log_file"
}

rehearse_requires_snapshot_id() {
  local output status

  output=$(bash "$SCRIPTS_DIR/rehearse.sh" 2>&1)
  status=$?

  [[ $status -ne 0 ]] && [[ $output == *"usage: rehearse.sh <snapshot-id>"* ]]
}

run_test cutover_requires_execute
run_test cutover_requires_rehearsal_id
run_test rollback_requires_snapshot_id
run_test rollback_rejects_unsafe_snapshot_id
run_test cleanup_requires_execute
run_test cleanup_requires_cutover_snapshot_id
run_test preflight_propagates_remote_fingerprint_failure
run_test preflight_rejects_changed_image_id
run_test production_compose_preserves_current_topology
run_test rehearsal_compose_is_private_and_media_read_only
run_test prepare_image_falls_back_to_arm64_transfer
run_test snapshot_restarts_production_when_copy_fails
run_test snapshot_creates_verified_copy_and_returns_id
run_test rehearse_requires_snapshot_id

if ((failures > 0)); then
  exit 1
fi
