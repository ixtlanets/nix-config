#!/usr/bin/env bash

set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  ./.opencode/scripts/bump-codex.sh [--dry-run] [version]

Examples:
  ./.opencode/scripts/bump-codex.sh
  ./.opencode/scripts/bump-codex.sh 0.130.0
  ./.opencode/scripts/bump-codex.sh --dry-run
EOF
}

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"
NIX_FILE="${REPO_ROOT}/overlays/default.nix"

if [[ ! -f "${NIX_FILE}" ]]; then
  echo "error: cannot find ${NIX_FILE}" >&2
  exit 1
fi

cd "${REPO_ROOT}"

DRY_RUN=0
TARGET_VERSION=""

while (($# > 0)); do
  case "$1" in
    --dry-run|-n)
      DRY_RUN=1
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      if [[ -n "${TARGET_VERSION}" ]]; then
        echo "error: only one version argument is allowed" >&2
        usage
        exit 1
      fi
      TARGET_VERSION="$1"
      ;;
  esac
  shift
done

if command -v git >/dev/null 2>&1; then
  if git -C "${REPO_ROOT}" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    if [[ -n "$(git -C "${REPO_ROOT}" status --porcelain)" ]]; then
      echo "warn: git tree is dirty; continuing and only updating overlays/default.nix" >&2
    fi
  fi
fi

if [[ -z "${TARGET_VERSION}" ]]; then
  latest_tag="$({
    curl -fsSL "https://api.github.com/repos/openai/codex/releases/latest"
  } | python3 -c 'import json, sys; print(json.load(sys.stdin)["tag_name"])')"
  TARGET_VERSION="${latest_tag#rust-v}"
  TARGET_VERSION="${TARGET_VERSION#v}"
fi

if [[ ! "${TARGET_VERSION}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "error: invalid version '${TARGET_VERSION}', expected X.Y.Z" >&2
  exit 1
fi

declare -a ORDER=(
  "linux-x64"
  "linux-arm64"
  "darwin-x64"
  "darwin-arm64"
)

declare -A ASSETS=(
  ["linux-x64"]="codex-x86_64-unknown-linux-musl.zst"
  ["linux-arm64"]="codex-aarch64-unknown-linux-musl.zst"
  ["darwin-x64"]="codex-x86_64-apple-darwin.zst"
  ["darwin-arm64"]="codex-aarch64-apple-darwin.zst"
)

declare -A URLS=()
for key in "${ORDER[@]}"; do
  URLS["$key"]="https://github.com/openai/codex/releases/download/rust-v${TARGET_VERSION}/${ASSETS[$key]}"
done

declare -A HASHES=()

fetchurl_hash() {
  local url="$1"
  local output status

  set +e
  output="$({
    nix-build -E "with import <nixpkgs> {}; fetchurl { url = \"${url}\"; sha256 = lib.fakeSha256; }"
  } 2>&1)"
  status=$?
  set -e

  if [[ "${status}" -eq 0 ]]; then
    echo "error: expected fake hash mismatch for ${url}" >&2
    exit 1
  fi

  OUTPUT="${output}" python3 - <<'PY'
import re
import os
import sys

text = os.environ["OUTPUT"]
match = re.search(r'got:\s+(sha256-[A-Za-z0-9+/=]+)', text)
if not match:
    print(text, file=sys.stderr)
    raise SystemExit("failed to parse fetchurl hash")
print(match.group(1))
PY
}

for key in "${ORDER[@]}"; do
  url="${URLS[$key]}"
  echo "prefetching ${key}..." >&2
  hash="$(fetchurl_hash "${url}")"
  HASHES["$key"]="${hash}"
done

current_version="$({
  python3 - "${NIX_FILE}" <<'PY'
import pathlib
import re
import sys

path = pathlib.Path(sys.argv[1])
text = path.read_text()
match = re.search(r'pname\s*=\s*"codex";\s*\n\s*version\s*=\s*"([^"]+)";', text)
if not match:
    raise SystemExit("failed to detect current codex version")
print(match.group(1))
PY
} )"

echo "current version: ${current_version}"
echo "target version:  ${TARGET_VERSION}"

for key in "${ORDER[@]}"; do
  echo "${key}: ${HASHES[$key]}"
done

if [[ "${DRY_RUN}" -eq 1 ]]; then
  echo "dry-run: no files changed"
  exit 0
fi

python3 - "${NIX_FILE}" "${TARGET_VERSION}" "${HASHES[linux-x64]}" "${HASHES[linux-arm64]}" "${HASHES[darwin-x64]}" "${HASHES[darwin-arm64]}" <<'PY'
import pathlib
import re
import sys

path = pathlib.Path(sys.argv[1])
version = sys.argv[2]
hash_by_file = {
    "codex-x86_64-unknown-linux-musl.zst": sys.argv[3],
    "codex-aarch64-unknown-linux-musl.zst": sys.argv[4],
    "codex-x86_64-apple-darwin.zst": sys.argv[5],
    "codex-aarch64-apple-darwin.zst": sys.argv[6],
}

text = path.read_text()

text, version_count = re.subn(
    r'(pname\s*=\s*"codex";\s*\n\s*version\s*=\s*")[^"]+(";)',
    rf'\g<1>{version}\2',
    text,
    count=1,
)
if version_count != 1:
    raise SystemExit("failed to update codex version line")

for asset, hash_value in hash_by_file.items():
    pattern = (
        rf'(url\s*=\s*"https://github.com/openai/codex/releases/download/rust-v\$\{{version\}}/{re.escape(asset)}";\n\s*sha256\s*=\s*")'
        r'[^"]+'
        r'(";)'
    )
    text, count = re.subn(pattern, rf'\g<1>{hash_value}\2', text, count=1)
    if count != 1:
        raise SystemExit(f"failed to update sha256 for {asset}")

path.write_text(text)
PY

echo "updated ${NIX_FILE}"
echo "running: nix build codex overlay package"
nix build --impure --expr "let flake = builtins.getFlake \"path:${REPO_ROOT}\"; system = builtins.currentSystem; pkgs = import flake.inputs.nixpkgs { inherit system; overlays = [ flake.outputs.overlays.modifications ]; config.allowUnfree = true; }; in pkgs.codex"

echo "success: codex bumped to ${TARGET_VERSION}"
