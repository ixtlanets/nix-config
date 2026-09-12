#!/usr/bin/env sh

set -eu

read_secret() {
  secret_path=$1
  if [ ! -f "$secret_path" ] || [ -L "$secret_path" ]; then
    echo "missing or unsafe container secret: $secret_path" >&2
    exit 1
  fi
  secret_value=$(cat -- "$secret_path")
  if [ -z "$secret_value" ]; then
    echo "empty container secret: $secret_path" >&2
    exit 1
  fi
  printf '%s' "$secret_value"
}

JWT_SECRET=$(read_secret /run/secrets/rmab-jwt-secret)
JWT_REFRESH_SECRET=$(read_secret /run/secrets/rmab-jwt-refresh-secret)
CONFIG_ENCRYPTION_KEY=$(read_secret /run/secrets/rmab-config-encryption-key)
POSTGRES_PASSWORD=$(read_secret /run/secrets/rmab-postgres-password)
export JWT_SECRET JWT_REFRESH_SECRET CONFIG_ENCRYPTION_KEY POSTGRES_PASSWORD

exec /entrypoint.sh "$@"
