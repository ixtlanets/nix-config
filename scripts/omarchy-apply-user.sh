#!/usr/bin/env bash
set -euo pipefail

source_root="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
expected_host="${OMARCHY_EXPECTED_HOST:-x1carbon}"

log() {
  printf '[omarchy:user] %s\n' "$*"
}

die() {
  printf '[omarchy:user] ERROR: %s\n' "$*" >&2
  exit 1
}

install_file() {
  local source="$1"
  local destination="$2"

  [[ -f "$source" ]] || die "source file missing: $source"
  mkdir -p "$(dirname "$destination")"
  if [[ -f "$destination" ]] && cmp -s "$source" "$destination"; then
    log "unchanged $destination"
    return
  fi
  install -m 0644 "$source" "$destination"
  log "installed $destination"
}

ensure_plugin() {
  local id="$1"
  local url="$2"
  local destination="$HOME/.config/omarchy/plugins/$id"

  if [[ -d "$destination" || -L "$destination" ]]; then
    log "plugin $id already installed"
    return
  fi

  log "installing plugin $id"
  omarchy plugin add "$url" --yes
}

configure_foot_shell() {
  local config="$HOME/.config/foot/foot.ini"
  local temporary

  [[ -f "$config" ]] || {
    mkdir -p "$(dirname "$config")"
    printf '[main]\nshell=/usr/bin/zsh\n' > "$config"
    log "configured Foot to launch Zsh"
    return
  }
  if /usr/bin/awk '
    /^\[main\]$/ { in_main = 1; next }
    /^\[/ { in_main = 0 }
    in_main && /^shell=\/usr\/bin\/zsh$/ { found = 1 }
    END { exit !found }
  ' "$config"; then
    log "unchanged $config shell"
    return
  fi

  temporary="$(mktemp "${config}.XXXXXX")"
  /usr/bin/awk '
    /^\[main\]$/ {
      print
      print "shell=/usr/bin/zsh"
      in_main = 1
      next
    }
    /^\[/ { in_main = 0 }
    in_main && /^shell=/ { next }
    { print }
  ' "$config" > "$temporary"
  install -m 0644 "$temporary" "$config"
  rm -f "$temporary"
  log "configured Foot to launch Zsh"
}

configure_cursor() {
  export XCURSOR_THEME="Bibata-Original-Ice"
  export XCURSOR_SIZE="24"

  if command -v gsettings >/dev/null 2>&1; then
    gsettings set org.gnome.desktop.interface cursor-theme "$XCURSOR_THEME"
    gsettings set org.gnome.desktop.interface cursor-size "$XCURSOR_SIZE"
  fi
  systemctl --user set-environment \
    XCURSOR_THEME="$XCURSOR_THEME" \
    XCURSOR_SIZE="$XCURSOR_SIZE"
  if command -v dbus-update-activation-environment >/dev/null 2>&1; then
    dbus-update-activation-environment --systemd XCURSOR_THEME XCURSOR_SIZE
  fi
  if command -v hyprctl >/dev/null 2>&1 && [[ -n "${HYPRLAND_INSTANCE_SIGNATURE:-}" ]]; then
    hyprctl setcursor "$XCURSOR_THEME" "$XCURSOR_SIZE"
  fi
}

[[ "$(hostname -s)" == "$expected_host" ]] ||
  die "hostname $(hostname -s) does not match $expected_host"
[[ -r /etc/os-release ]] || die "/etc/os-release is missing"
# shellcheck disable=SC1091
source /etc/os-release
[[ "${ID:-}" == omarchy ]] || die "host is not Omarchy"
command -v omarchy >/dev/null 2>&1 || die "omarchy command is missing"
[[ "$(id -u)" -ne 0 ]] || die "run as desktop user, not root"
export OMARCHY_PATH="${OMARCHY_PATH:-/usr/share/omarchy}"

while IFS= read -r variable; do
  export "${variable?}"
done < <(systemctl --user show-environment | grep -E \
  '^(DBUS_SESSION_BUS_ADDRESS|DISPLAY|HYPRLAND_INSTANCE_SIGNATURE|WAYLAND_DISPLAY|XDG_CURRENT_DESKTOP|XDG_RUNTIME_DIR)=')

ensure_plugin \
  io.github.sspaeti.timezones \
  https://github.com/sspaeti/omarchy-timezones-plugin.git
ensure_plugin \
  io.github.snikulin.omaquote \
  https://github.com/snikulin/omaquote.git

install_file "$source_root/dotfiles/omarchy/zshrc" "$HOME/.zshrc"
install_file "$source_root/dotfiles/omarchy/starship.toml" "$HOME/.config/starship.toml"
install_file "$source_root/dotfiles/omarchy/shell.json" "$HOME/.config/omarchy/shell.json"
install_file "$source_root/dotfiles/omarchy/voxtype/config.toml" "$HOME/.config/voxtype/config.toml"
install_file "$source_root/dotfiles/omarchy/bin/vless" "$HOME/.local/bin/vless"
chmod 0755 "$HOME/.local/bin/vless"
install_file "$source_root/dotfiles/omarchy/environment.d/cursor.conf" "$HOME/.config/environment.d/20-cursor.conf"
install_file "$source_root/dotfiles/omarchy/icons/default/index.theme" "$HOME/.icons/default/index.theme"
install_file "$source_root/dotfiles/omarchy/hypr/input.lua" "$HOME/.config/hypr/input.lua"
install_file "$source_root/dotfiles/omarchy/hypr/bindings.lua" "$HOME/.config/hypr/bindings.lua"
install_file "$source_root/dotfiles/omarchy/hypr/looknfeel.lua" "$HOME/.config/hypr/looknfeel.lua"
install_file "$source_root/dotfiles/omarchy/yt-dlp/config" "$HOME/.config/yt-dlp/config"
configure_foot_shell
configure_cursor
omarchy-shell shell rescanPlugins >/dev/null

git config --global user.name "Sergey Nikulin"
git config --global user.email "snikulin@gmail.com"
git config --global init.defaultBranch master

if command -v pass >/dev/null 2>&1 && [[ ! -d "$HOME/.password-store" ]]; then
  log "cloning password store"
  git clone git@github.com:snikulin/.password-store.git "$HOME/.password-store" ||
    log "warning: password store clone failed; retry after checking GitHub SSH access"
fi

if command -v syncthing >/dev/null 2>&1 && [[ -f "$HOME/.local/state/syncthing/cert.pem" ]]; then
  systemctl --user enable --now syncthing.service
fi

if command -v voxtype >/dev/null 2>&1 &&
  [[ -f "$HOME/.local/share/voxtype/models/parakeet-tdt-0.6b-v3/encoder-model.onnx.data" ]]; then
  systemctl --user enable --now voxtype.service
fi

if command -v zsh >/dev/null 2>&1; then
  zsh -n "$HOME/.zshrc"
else
  log "warning: zsh not installed yet"
fi

if command -v hyprctl >/dev/null 2>&1 && [[ -n "${HYPRLAND_INSTANCE_SIGNATURE:-}" ]]; then
  hyprctl reload
  if [[ -n "$(hyprctl configerrors)" ]]; then
    hyprctl configerrors >&2
    die "Hyprland reported configuration errors"
  fi
else
  log "Hyprland reload skipped outside graphical session"
fi

log "user configuration applied"
