#!/usr/bin/env bash
set -euo pipefail

[[ "$(voxtype setup onnx --status 2>&1)" == *'Backend: ONNX'* ]] ||
  sudo voxtype setup onnx --enable
if [[ ! -f "$HOME/.local/share/voxtype/models/parakeet-tdt-0.6b-v3/encoder-model.onnx.data" ]]; then
  voxtype setup \
    --download \
    --model parakeet-tdt-0.6b-v3 \
    --quiet \
    --no-post-install
fi
systemctl --user enable --now voxtype.service
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
