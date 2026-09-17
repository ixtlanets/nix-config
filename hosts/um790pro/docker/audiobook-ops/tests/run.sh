#!/usr/bin/env bash

set -euo pipefail

bundle_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
export PYTHONPATH="$bundle_dir/src${PYTHONPATH:+:$PYTHONPATH}"
exec python -m unittest discover -s "$bundle_dir/tests" -v
