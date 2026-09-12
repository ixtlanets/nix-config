#!/usr/bin/env bash

set -euo pipefail
umask 077

password_file=${AUDIOBOOK_OPS_TRANSMISSION_PASSWORD_FILE:-/run/secrets/transmission_password}
transmission_init=${AUDIOBOOK_OPS_TRANSMISSION_INIT:-/init}

if [[ ! -f $password_file || -L $password_file ]]; then
  echo "Transmission password secret is missing or unsafe" >&2
  exit 1
fi

mapfile -t password_lines <"$password_file"
if [[ ${#password_lines[@]} -ne 1 || -z ${password_lines[0]} ]]; then
  echo "Transmission password secret must contain exactly one non-empty line" >&2
  exit 1
fi

export PASS=${password_lines[0]}
unset password_lines FILE__PASS

if [[ ! -x $transmission_init ]]; then
  echo "Transmission init is not executable" >&2
  exit 1
fi

exec "$transmission_init" "$@"
