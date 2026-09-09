#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
config="$repo_root/dotfiles/omarchy/herdr/config.toml"
apply_user="$repo_root/scripts/omarchy-apply-user.sh"
verify="$repo_root/scripts/omarchy-verify.sh"

[[ -f "$config" ]] || {
  printf 'Missing managed Omarchy herdr config: %s\n' "$config" >&2
  exit 1
}

[[ "$(HERDR_CONFIG_PATH="$config" herdr config check)" == "config: ok" ]]

python - "$config" <<'PY'
import sys
import tomllib

with open(sys.argv[1], "rb") as config_file:
    config = tomllib.load(config_file)

terminal = config["terminal"]
assert terminal == {
    "default_shell": "/usr/bin/zsh",
    "shell_mode": "login",
    "new_cwd": "follow",
}

keys = config["keys"]
assert keys["prefix"] == "ctrl+b"
assert keys["split_horizontal"] == ["prefix+minus", "alt+enter"]
assert keys["split_vertical"] == ["prefix+v", "alt+shift+enter"]
assert keys["close_tab"] == "prefix+shift+x"
assert keys["close_workspace"] == "prefix+shift+d"
for direction, key in (("left", "h"), ("down", "j"), ("up", "k"), ("right", "l")):
    assert f"prefix+{key}" in keys[f"focus_pane_{direction}"]
    assert f"prefix+shift+{key}" in keys[f"resize_pane_{direction}"]

assert config["ui"]["agent_panel_sort"] == "priority"
PY

grep -Fq 'install_herdr_config' "$apply_user"
grep -Fq 'omarchy restart herdr' "$apply_user"
grep -Fq 'dotfiles/omarchy/herdr/config.toml' "$verify"
grep -Fq 'herdr config check' "$verify"

printf 'PASS: Omarchy herdr config preserves the tmux workflow\n'
