#!/usr/bin/env bash
set -euo pipefail

[[ "$(voxtype setup onnx --status 2>&1)" == *'Backend: ONNX'* ]] ||
  sudo voxtype setup onnx --enable
systemctl --user restart voxtype.service

for _ in {1..20}; do
  if [[ "$(systemctl --user is-active voxtype.service)" == active ]]; then
    printf '[omarchy:voxtype] ONNX backend and service are active.\n'
    sleep 5
    exit 0
  fi
  sleep 1
done

systemctl --user status voxtype.service --no-pager -l || true
printf '[omarchy:voxtype] Service did not become active. Press Enter to close.\n' >&2
read -r _
exit 1
