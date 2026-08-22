#!/usr/bin/env bash

BUNDLE_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
REMOTE=${REMOTE:-moscow}
SSH_BIN=${SSH_BIN:-ssh}
DOCKER_BIN=${DOCKER_BIN:-docker}
SCP_BIN=${SCP_BIN:-scp}

EXPECTED_HOSTNAME=rpi4
EXPECTED_ARCH=aarch64
EXPECTED_CURRENT_IMAGE_ID=sha256:b83b66d7c1f3fec8bdea64f7ef670a9b7b61d8ab227d279b3d65551a877851ad
EXPECTED_TARGET_IMAGE_ID=sha256:28b665b047a1e02474fad2bc703bd2a7489e4e72295f67e431c17f07c63320b3
EXPECTED_TARGET_INDEX_DIGEST=sha256:180acad33d69c99ed208676465d8edcb268fa46967735579a7810859885b1a8e
EXPECTED_TARGET_MANIFEST_DIGEST=sha256:14a6492c743f2acfa00bcd96ec2a5c0c95e311f567718d29cb3c7f3772dc773f
TARGET_IMAGE=ghcr.io/advplyr/audiobookshelf:2.36.0
DEPLOYMENT_IMAGE=nix-config/audiobookshelf:2.36.0-arm64-14a6492c

REMOTE_BUNDLE_DIR=${REMOTE_BUNDLE_DIR:-/home/nik/.local/share/nix-config-services/audiobookshelf}
REMOTE_STATE_DIR=${REMOTE_STATE_DIR:-/home/nik/.local/state/audiobookshelf}
SOURCE_STATE_DIR=${SOURCE_STATE_DIR:-/media/disk1/media/meta}
MEDIA_DIR=${MEDIA_DIR:-/media/disk1/media/Audiobooks}
TAILSCALE_IP=${TAILSCALE_IP:-100.81.67.47}

run_remote() {
  "$SSH_BIN" "$REMOTE" bash -s
}

sync_bundle() {
  case "$REMOTE_BUNDLE_DIR" in
    /home/nik/*) ;;
    *)
      echo "unsafe remote bundle directory: $REMOTE_BUNDLE_DIR" >&2
      return 1
      ;;
  esac
  [[ $REMOTE_BUNDLE_DIR =~ ^/home/nik/[A-Za-z0-9._/-]+$ ]] || {
    echo "unsupported characters in remote bundle directory" >&2
    return 1
  }

  "$SSH_BIN" "$REMOTE" "install -d -m 0755 '$REMOTE_BUNDLE_DIR'"
  "$SCP_BIN" \
    "$BUNDLE_DIR/docker-compose.yml" \
    "$BUNDLE_DIR/docker-compose.rehearsal.yml" \
    "$REMOTE:$REMOTE_BUNDLE_DIR/"
}
