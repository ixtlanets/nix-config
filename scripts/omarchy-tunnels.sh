#!/usr/bin/env bash

if (( $# != 0 )); then
  echo "Usage: omarchy-tunnels" >&2
  exit 1
fi

exec ssh -N -T \
  -i "$HOME/.ssh/id_rsa_1" \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -L 127.0.0.1:4177:127.0.0.1:4177 \
  -L 127.0.0.1:5178:127.0.0.1:5178 \
  -L 127.0.0.1:8082:127.0.0.1:8082 \
  omarchy-vm
