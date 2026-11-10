#!/usr/bin/env bash
# Isolated installer routing checks: never invokes real lifecycle/systemctl/mise.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
# TMP is an existing, verified temporary directory, never an arbitrary input.
[[ "$TMP" == /tmp/* && -d "$TMP" ]] || exit 1
trap 'rm -rf -- "${TMP:?}"' EXIT
mkdir -p "$TMP/tools" "$TMP/home"
export TEST_CALLS="$TMP/calls"

printf '%s\n' '#!/usr/bin/bash' 'printf "%s\\n" "$@" > "$TEST_CALLS"' > "$TMP/tools/bash"
chmod 700 "$TMP/tools/bash"
HOME="$TMP/home" PATH="$TMP/tools:/usr/bin:/bin" \
  /usr/bin/bash "$ROOT/install.sh" --dsh-local sentinel
mapfile -t calls < "$TEST_CALLS"
[[ "${calls[0]}" == "$ROOT/scripts/install-dsh-local.sh" && "${calls[1]}" == sentinel ]]
[[ ${#calls[@]} == 2 ]]

printf '%s\n' '#!/usr/bin/bash' \
  '[[ "${1:-}" == -c ]] && exit 0' \
  'printf "%s\\n" "$@" > "$TEST_CALLS"' > "$TMP/tools/python3"
chmod 700 "$TMP/tools/python3"
HOME="$TMP/home" PATH="$TMP/tools:/usr/bin:/bin" \
  /usr/bin/bash "$ROOT/scripts/install-dsh-local.sh" sentinel
mapfile -t calls < "$TEST_CALLS"
[[ "${calls[0]}" == "$ROOT/dotfiles/dsh/local/dsh-local" && "${calls[1]}" == install && "${calls[2]}" == sentinel ]]
[[ ${#calls[@]} == 3 ]]
[[ ! -e "$TMP/home/.dsh" ]]
# The real rc.1 launcher requires an explicit profile; a mocked mise alone
# cannot catch accidentally starting `dsh --no-open` without `web`.
/usr/bin/python3 - "$ROOT" <<'PY'
from pathlib import Path
import shlex
import sys
runtime = (Path(sys.argv[1]) / 'dotfiles/dsh/local/dsh-local-runtime').read_text()
command = next(line for line in runtime.replace('\\\n', ' ').splitlines() if line.startswith('exec '))
args = shlex.split(command)
app = args[args.index('--') + 1:]
assert app[0] == 'dsh', app
assert app[1] == 'web' or app[1:3] == ['--profile', 'web'], 'DSH requires the explicit web profile'
PY
printf 'Local installer routing, profile selection, and no profile seeding: passed\n'
