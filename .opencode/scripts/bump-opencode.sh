#!/usr/bin/env bash

set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  ./.opencode/scripts/bump-opencode.sh [--dry-run] [version]

Examples:
  ./.opencode/scripts/bump-opencode.sh
  ./.opencode/scripts/bump-opencode.sh 1.2.21
  ./.opencode/scripts/bump-opencode.sh --dry-run
EOF
}

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"
NIX_FILE="${REPO_ROOT}/pkgs/opencode.nix"

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
      echo "warn: git tree is dirty; continuing and only updating pkgs/opencode.nix" >&2
    fi
  fi
fi

if [[ -z "${TARGET_VERSION}" ]]; then
  latest_tag="$({
    curl -fsSL "https://api.github.com/repos/anomalyco/opencode/releases/latest"
  } | python3 -c 'import json, sys; print(json.load(sys.stdin)["tag_name"])')"
  TARGET_VERSION="${latest_tag#v}"
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

declare -A URLS=(
  ["linux-x64"]="https://github.com/anomalyco/opencode/releases/download/v${TARGET_VERSION}/opencode-linux-x64.tar.gz"
  ["linux-arm64"]="https://github.com/anomalyco/opencode/releases/download/v${TARGET_VERSION}/opencode-linux-arm64.tar.gz"
  ["darwin-x64"]="https://github.com/anomalyco/opencode/releases/download/v${TARGET_VERSION}/opencode-darwin-x64.zip"
  ["darwin-arm64"]="https://github.com/anomalyco/opencode/releases/download/v${TARGET_VERSION}/opencode-darwin-arm64.zip"
)

declare -A HASHES=()

for key in "${ORDER[@]}"; do
  url="${URLS[$key]}"
  echo "prefetching ${key}..." >&2
  hash="$({
    nix store prefetch-file --json --unpack "${url}"
  } | python3 -c 'import json, sys; print(json.load(sys.stdin)["hash"])')"
  HASHES["$key"]="${hash}"
done

current_version="$({
  python3 - "${NIX_FILE}" <<'PY'
import pathlib
import re
import sys

path = pathlib.Path(sys.argv[1])
text = path.read_text()
match = re.search(r'\bversion\s*=\s*"([^"]+)";', text)
if not match:
    raise SystemExit("failed to detect current opencode version")
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
    "opencode-linux-x64.tar.gz": sys.argv[3],
    "opencode-linux-arm64.tar.gz": sys.argv[4],
    "opencode-darwin-x64.zip": sys.argv[5],
    "opencode-darwin-arm64.zip": sys.argv[6],
}

text = path.read_text()

text, version_count = re.subn(
    r'(\bversion\s*=\s*")[^"]+(";)',
    rf'\g<1>{version}\2',
    text,
    count=1,
)
if version_count != 1:
    raise SystemExit("failed to update version line")

for asset, hash_value in hash_by_file.items():
    pattern = (
        rf'(url\s*=\s*"https://github.com/anomalyco/opencode/releases/download/v\$\{{version\}}/{re.escape(asset)}";\n\s*sha256\s*=\s*")'
        r'[^"]+'
        r'(";)'
    )
    text, count = re.subn(pattern, rf'\g<1>{hash_value}\2', text, count=1)
    if count != 1:
        raise SystemExit(f"failed to update sha256 for {asset}")

path.write_text(text)
PY

echo "updated ${NIX_FILE}"
echo "running: nix build .#opencode"
nix build .#opencode

echo "success: opencode bumped to ${TARGET_VERSION}"
