#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
config="$repo_root/dotfiles/omarchy/tmux/tmux.conf"
tmp_dir="$(mktemp -d)"
socket="$tmp_dir/tmux.sock"
test_home="$tmp_dir/home"
plugins_dir="$tmp_dir/managed-plugins"

cleanup() {
  tmux -S "$socket" kill-server >/dev/null 2>&1 || true
  rm -rf "$tmp_dir"
}
trap cleanup EXIT

[[ -f "$config" ]] || {
  printf 'Missing managed Omarchy tmux config: %s\n' "$config" >&2
  exit 1
}

mkdir -p "$test_home/.config/tmux" "$plugins_dir/tpm"
cp "$config" "$test_home/.config/tmux/tmux.conf"
cat > "$plugins_dir/tpm/tpm" <<MOCK
#!/bin/sh
: > "$tmp_dir/tpm-loaded"
MOCK
chmod +x "$plugins_dir/tpm/tpm"

# Model first provision while a tmux server with the previous config is active.
HOME="$test_home" XDG_CONFIG_HOME="$test_home/.config" \
  tmux -S "$socket" -f /dev/null new-session -d -s config-test
tmux -S "$socket" start-server \; set-environment -g TMUX_PLUGIN_MANAGER_PATH "$plugins_dir/"
HOME="$test_home" XDG_CONFIG_HOME="$test_home/.config" \
  tmux -S "$socket" source-file "$config"

[[ "$(tmux -S "$socket" show-options -gv default-shell)" == /usr/bin/zsh ]]
[[ "$(tmux -S "$socket" show-options -gv default-command)" == '/usr/bin/zsh -l' ]]
[[ "$(tmux -S "$socket" show-options -gv base-index)" == 1 ]]
[[ "$(tmux -S "$socket" show-window-options -gv pane-base-index)" == 1 ]]
[[ "$(tmux -S "$socket" show-window-options -gv mode-keys)" == vi ]]
[[ "$(tmux -S "$socket" show-window-options -gv clock-mode-style)" == 24 ]]
[[ "$(tmux -S "$socket" show-options -gv @dracula-plugins)" == \
  'battery cpu-usage ram-usage time' ]]
[[ "$(tmux -S "$socket" show-environment -g TMUX_PLUGIN_MANAGER_PATH)" == \
  "TMUX_PLUGIN_MANAGER_PATH=$plugins_dir/" ]]
[[ -f "$tmp_dir/tpm-loaded" ]]
update_environment="$(tmux -S "$socket" show-options -gv update-environment)"
grep -Fxq TERM <<< "$update_environment"
grep -Fxq TERM_PROGRAM <<< "$update_environment"
for plugin in \
  tmux-plugins/tpm \
  tmux-plugins/tmux-sensible \
  tmux-plugins/tmux-pain-control \
  tmux-plugins/tmux-urlview \
  tmux-plugins/tmux-prefix-highlight \
  dracula/tmux; do
  grep -Fqx "set -g @plugin '$plugin'" "$config"
done

printf 'PASS: Omarchy tmux config preserves the NixOS behavior\n'
