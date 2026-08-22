#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

inspect_output=$("$DOCKER_BIN" buildx imagetools inspect "$TARGET_IMAGE")
grep -Fq "$EXPECTED_TARGET_INDEX_DIGEST" <<<"$inspect_output" || {
  echo "target OCI index digest mismatch" >&2
  exit 1
}
grep -Fq "$EXPECTED_TARGET_MANIFEST_DIGEST" <<<"$inspect_output" || {
  echo "target ARM64 manifest digest mismatch" >&2
  exit 1
}

if "$SSH_BIN" "$REMOTE" docker pull "$TARGET_IMAGE"; then
  echo "native remote pull succeeded"
else
  echo "native remote pull failed; using single-platform ARM64 transfer" >&2
  "$DOCKER_BIN" pull --platform linux/arm64 "$TARGET_IMAGE"

  local_image_id=$("$DOCKER_BIN" image inspect "$TARGET_IMAGE" --format '{{.Id}}')
  [[ $local_image_id == "$EXPECTED_TARGET_IMAGE_ID" ]] || {
    echo "local ARM64 image ID mismatch" >&2
    exit 1
  }

  "$DOCKER_BIN" save "$TARGET_IMAGE" | "$SSH_BIN" "$REMOTE" docker load
fi

remote_image_id=$("$SSH_BIN" "$REMOTE" docker image inspect "$TARGET_IMAGE" --format '{{.Id}}')
[[ $remote_image_id == "$EXPECTED_TARGET_IMAGE_ID" ]] || {
  echo "remote ARM64 image ID mismatch" >&2
  exit 1
}

"$SSH_BIN" "$REMOTE" docker tag "$TARGET_IMAGE" "$DEPLOYMENT_IMAGE"
deployment_image_id=$("$SSH_BIN" "$REMOTE" docker image inspect "$DEPLOYMENT_IMAGE" --format '{{.Id}}')
[[ $deployment_image_id == "$EXPECTED_TARGET_IMAGE_ID" ]] || {
  echo "deployment image ID mismatch" >&2
  exit 1
}

printf 'target image prepared: %s (%s)\n' "$DEPLOYMENT_IMAGE" "$deployment_image_id"
