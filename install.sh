#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOSTNAME_SHORT="$(hostname -s 2>/dev/null || hostname)"
GIT_USER_NAME="Sergey Nikulin"
GIT_USER_EMAIL="snikulin@gmail.com"

log() {
  echo "[install:zsh] $*"
}

pacman_install() {
  local pkg="$1"
  if pacman -Qi "$pkg" >/dev/null 2>&1; then
    log "${pkg} already installed"
    return 0
  fi

  if pacman -Si "$pkg" >/dev/null 2>&1; then
    log "installing ${pkg} via pacman"
    sudo pacman --noconfirm --needed -S "$pkg"
    return 0
  fi

  if command -v yay >/dev/null 2>&1; then
    if yay -Qi "$pkg" >/dev/null 2>&1; then
      log "${pkg} already installed (yay)"
      return 0
    fi
    if yay -Si "$pkg" >/dev/null 2>&1; then
      log "installing ${pkg} via yay"
      yay --noconfirm --needed -S "$pkg"
      return 0
    fi
  fi

  log "warning: package ${pkg} not found in pacman or yay"
}

npm_global_install() {
  local pkg="$1"
  if npm list -g "$pkg" >/dev/null 2>&1; then
    log "npm global package ${pkg} already installed"
    return
  fi
  log "installing npm global package ${pkg}"
  sudo npm install -g "$pkg"
}

ensure_yay() {
  if command -v yay >/dev/null 2>&1; then
    log "yay already installed"
    return
  fi

  log "installing yay from AUR (requires base-devel and git)"
  pacman_install base-devel
  pacman_install git

  local tmpdir
  tmpdir="$(mktemp -d)"
  trap 'rm -rf "$tmpdir"' EXIT
  git clone https://aur.archlinux.org/yay.git "$tmpdir/yay"
  pushd "$tmpdir/yay" >/dev/null
  makepkg -si --noconfirm
  popd >/dev/null
}

configure_nix() {
  if ! command -v nix >/dev/null 2>&1; then
    log "nix is not installed; skipping nix configuration"
    return
  fi

  if command -v systemctl >/dev/null 2>&1; then
    log "enabling and starting nix-daemon.service"
    sudo systemctl enable --now nix-daemon.service
  else
    log "systemctl not found; skipping nix-daemon enablement"
  fi

  local nix_conf="/etc/nix/nix.conf"
  log "configuring ${nix_conf}"
  sudo mkdir -p /etc/nix
  sudo tee "$nix_conf" >/dev/null <<'EOF'
experimental-features = nix-command flakes
trusted-users = root nik
substituters = https://cache.nixos.org https://devenv.cachix.org https://cache.flox.dev
trusted-substituters = https://cache.flox.dev
trusted-public-keys = cache.nixos.org-1:6NCHdD59X431o0gWypbMrAURkbJ16ZPMQFGspcDShjY= devenv.cachix.org-1:w1cLUi8dv3hnoSPGAuibQv+f9TZtWKshxzYfXc0fJyQ= flox-cache-public-1:7F4OyH7ZCnFhcze3fJdfyXYLQw/aV7GEed86nQ7IsOs=
build-users-group = nixbld
EOF

  if command -v systemctl >/dev/null 2>&1; then
    sudo systemctl restart nix-daemon.service
  fi
}

install_devenv() {
  if ! command -v nix >/dev/null 2>&1; then
    log "nix not available; skipping devenv install"
    return
  fi

  if nix profile list 2>/dev/null | grep -q 'nixpkgs#devenv'; then
    log "devenv already installed in nix profile"
    return
  fi

  log "installing devenv via nix profile"
  nix profile install nixpkgs#devenv
}

install_tz() {
  if command -v tz >/dev/null 2>&1; then
    log "tz already installed"
    return
  fi

  if ! command -v go >/dev/null 2>&1; then
    log "go not available; skipping tz install"
    return
  fi

  log "installing tz via go install"
  mkdir -p "${HOME}/.local/bin"
  GOBIN="${HOME}/.local/bin" go install github.com/oz/tz@latest
}

configure_git_defaults() {
  log "configuring global git defaults"
  git config --global user.name "$GIT_USER_NAME"
  git config --global user.email "$GIT_USER_EMAIL"
  git config --global init.defaultBranch "master"
  git config --global diff.tool "diff-so-fancy"
  git config --global core.pager "diff-so-fancy | less --tabs=4 -RFX"
}

enable_sshd_service() {
  if command -v systemctl >/dev/null 2>&1; then
    log "enabling and starting sshd.service"
    sudo systemctl enable --now sshd.service
  else
    log "systemctl not found; skip enabling sshd.service"
  fi
}

configure_openssh() {
  local ssh_dir="${HOME}/.ssh"
  mkdir -p "$ssh_dir"
  chmod 700 "$ssh_dir"

  local ssh_files=(
    "id_rsa:600"
    "id_rsa.pub:644"
    "id_rsa_1:600"
    "id_rsa_1.pub:644"
    "startspiritup-firebase-adminsdk-o9eey-c7292ac3f8.json:600"
  )

  for entry in "${ssh_files[@]}"; do
    IFS=: read -r filename mode <<<"$entry"
    local src="${SCRIPT_DIR}/secrets/ssh/${filename}"
    local dest="${ssh_dir}/${filename}"
    if [[ -f "$src" ]]; then
      log "installing ssh key ${filename}"
      install -m"$mode" "$src" "$dest"
    else
      log "warning: ssh key ${filename} not found at ${src}; skipping"
    fi
  done

  local auth_file="${ssh_dir}/authorized_keys"
  local authorized_keys=(
    "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQC35qP3UeDJNWzN1ux5FY6Mnsj7KLAmRRt254vjz1Ry5SNwdLE1VhVPVnmIufyKWK5/z6g8NiPvFxXzAyKCitpSS6ahYQjKCXS9b5P3C+FPLcwcy1Ge54Fdu1qGzTeElbIm86+MSA1aQgwbzVfHQYl/TLBk7QVTJ5SdQgdBe7w3tt4hkQMhsqTue6FKF0sTF3xMcKf8B/CSmYHgFiVZsiqg+hb8sYBogIc5vsFlNfxg14UMriGh6/wOvNvZIn7IwgGB2tKGCEtS4p9PL7Vd+LHYUgwta2a/KXgH3xQEuCKDwGPJWpE4kkbSr1SNdQuGZP3Ry9Ta5TMIEgQ8n0mAD9lR nik@msi-ubuntu"
    "ssh-rsa AAAAB3NzaC1yc2EAAAABJQAAAQEAtj2ANdOntRVwWXdMm9FWu2fwDZNH2uEJH+vI37AfPwlmITtxBsOCM9/CYK/wkQa2elfkgkRYqvww0IlwCzI9/88t9YX7CWZU7z/P8ISufNL5VUOfiu15712CJjieauLOzTbAvyFvPhhqTkOpk/Fe1Mi1kFVaBlLqZjHsgokViACOmi+P06XFj0Bl//zAYvqC7mFSRGKDjmicW6vnUxShH6r4QQJv9J2z4KrDHs1ZWUOyWabqaVR4qD/vuGg2kYF/J1YaLKnNQGVNVtSmsaDbwTmev5dPKpZIxgRzl+MyaHDaCCxnzp6dHnjnlP8cfFW55t3Aea5JQCW8vtRrrwKExQ=="
    "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQCgv72CRql2CHmORIPFv4bgLNbdWQbgKbb4VOHqIBnoWddXi1PfoDuhesKrLwr+tvuNcOVzdPo69nh6NhXMsOW3it7FHeEsZ9ADH8W6PiZyEItDvTtrI6j6776ZGsn+pJ0Mj+qP4fZrSkmdd13tiKiigkX5Sif04vlTDGyQiL8zVOiigEO0UIUfTlw45KrE8/iqVnCoVzcaVqQ7QjNUOhGeiKihoIcyco++XiS1Qs2nw8oSvXphQ6KGjGMq1adGl7+4HEYJgkjN0dQqfkZzZtY5TfwKOFGKofj/TRP+pntBbl8RhtBwPpI7lbEQljv715PwYgAHVYhWuOlBQhskGz5L nik@ubuntu-server"
  )

  touch "$auth_file"
  chmod 600 "$auth_file"

  for key in "${authorized_keys[@]}"; do
    if grep -qxF "$key" "$auth_file"; then
      continue
    fi

    local comment="${key##* }"
    log "adding authorized key ${comment}"
    echo "$key" >>"$auth_file"
  done

  enable_sshd_service
}

configure_gpg() {
  if ! command -v gpg >/dev/null 2>&1; then
    log "gpg not available; skipping gpg setup"
    return
  fi

  local gpg_dir="${HOME}/.gnupg"
  local agent_conf="${gpg_dir}/gpg-agent.conf"
  mkdir -p "$gpg_dir"
  chmod 700 "$gpg_dir"

  if [[ -f "$agent_conf" ]]; then
    if ! grep -q "^enable-ssh-support" "$agent_conf"; then
      log "adding enable-ssh-support to ${agent_conf}"
      echo "enable-ssh-support" >>"$agent_conf"
    fi
  else
    log "writing ${agent_conf} with ssh support"
    echo "enable-ssh-support" >"$agent_conf"
  fi
  chmod 600 "$agent_conf"

  local public_key="${SCRIPT_DIR}/secrets/gpg/public.key"
  local private_key="${SCRIPT_DIR}/secrets/gpg/private.key"
  if [[ ! -f "$public_key" || ! -f "$private_key" ]]; then
    log "gpg key files not found; skipping import"
    return
  fi

  if gpg --list-secret-keys 2>/dev/null | grep -q "$GIT_USER_EMAIL"; then
    log "gpg keys for ${GIT_USER_EMAIL} already present"
    return
  fi

  log "importing gpg keys for ${GIT_USER_EMAIL}"
  gpg --import "$public_key"
  gpg --import "$private_key"
}

clone_password_store() {
  local pass_dir="${HOME}/.password-store"

  if [[ -d "${pass_dir}/.git" ]]; then
    log "password store already present at ${pass_dir}"
    return
  fi

  if ! command -v git >/dev/null 2>&1; then
    log "git not available; skipping password store clone"
    return
  fi

  log "cloning password store into ${pass_dir}"
  if git clone git@github.com:snikulin/.password-store.git "$pass_dir"; then
    log "password store cloned"
  else
    log "warning: failed to clone password store; check SSH access and gpg setup"
  fi
}

write_zshrc() {
  log "writing ${HOME}/.zshrc"
  cat <<'EOF' >"$HOME/.zshrc"
# Zsh config derived from nix-config (CachyOS/Arch)

# Ensure Nix paths are available even in non-login shells
if [[ -e /nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh ]]; then
  source /nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh
elif [[ -e /etc/profile.d/nix.sh ]]; then
  source /etc/profile.d/nix.sh
elif [[ -e "$HOME/.nix-profile/etc/profile.d/nix.sh" ]]; then
  source "$HOME/.nix-profile/etc/profile.d/nix.sh"
fi

export PATH="$HOME/.nix-profile/bin:/nix/var/nix/profiles/default/bin:$HOME/.local/bin:$HOME/go/bin:$PATH"
# Time zone list for tz (keep in sync with home-manager common.nix)
export TZ_LIST="Europe/London,London;America/New_York,NY;America/Los_Angeles,GR-office;Europe/Berlin,Berlin"
export PASSWORD_STORE_DIR="$HOME/.password-store"
export GPG_TTY="$(tty)"

# Aliases (keep in sync with home-manager common.nix)
alias gst="git status"

# History tuning
HISTFILE="$HOME/.zsh_history"
HISTSIZE=100000
SAVEHIST=100000
setopt HIST_IGNORE_DUPS
setopt HIST_EXPIRE_DUPS_FIRST

# Use emacs keybindings
bindkey -e

# Completion
mkdir -p "${XDG_CACHE_HOME:-$HOME/.cache}"
autoload -U compinit
compinit -d "${XDG_CACHE_HOME:-$HOME/.cache}/zcompdump"

# Plugins
if [[ -r /usr/share/zsh/plugins/zsh-autosuggestions/zsh-autosuggestions.zsh ]]; then
  source /usr/share/zsh/plugins/zsh-autosuggestions/zsh-autosuggestions.zsh
fi

if [[ -r /usr/share/zsh/plugins/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh ]]; then
  source /usr/share/zsh/plugins/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh
fi

# FZF extras
if [[ -r /usr/share/fzf/completion.zsh ]]; then
  source /usr/share/fzf/completion.zsh
fi
if [[ -r /usr/share/fzf/key-bindings.zsh ]]; then
  source /usr/share/fzf/key-bindings.zsh
fi

# Direnv hook
if command -v direnv >/dev/null 2>&1; then
  eval "$(direnv hook zsh)"
fi

# Prompt
if command -v starship >/dev/null 2>&1; then
  eval "$(starship init zsh)"
fi
EOF
}

write_starship_config() {
  local starship_dir="${XDG_CONFIG_HOME:-$HOME/.config}"
  mkdir -p "$starship_dir"
  log "writing ${starship_dir}/starship.toml"
  cat <<'EOF' >"${starship_dir}/starship.toml"
add_newline = false
format = "$nix_shell$username$hostname$directory$container$git_branch $git_status$python$nodejs$lua$rust$java$c$golang$status$character"
right_format = "$battery$time"

[battery]
full_symbol = ""
charging_symbol = ""
discharging_symbol = ""
unknown_symbol = ""
format = "[$symbol$percentage]($style)"

[time]
format = "[$time]($style)"

[status]
symbol = "✗"
not_found_symbol = "󰍉 Not Found"
not_executable_symbol = " Can't Execute E"
sigint_symbol = "󰂭 "
signal_symbol = "󱑽 "
success_symbol = ""
format = "[$symbol](fg:red)"
map_symbol = true
disabled = false

[character]
success_symbol = "[❯](bold purple)"
error_symbol = "[❯](bold red)"

[nix_shell]
disabled = false
format = "[](fg:white)[ ](bg:white fg:black)[](fg:white) "

[container]
symbol = " 󰏖"
format = "[$symbol ](yellow dimmed)"

[username]
show_always = true
style_user = "yellow"
style_root = "red"
format = "[$user]($style)"

[hostname]
ssh_only = false
format = "[@$hostname]($style): "
style = "green"

[directory]
format = "[$path]($style)[$read_only]($read_only_style) "
style = "blue"
read_only = " "
fish_style_pwd_dir_length = 1

[git_branch]
symbol = ""
style = ""
format = "[ $symbol $branch](fg:purple)(:$remote_branch)"

[python]
symbol = ""
format = "[$symbol ](yellow)"

[nodejs]
symbol = " "
format = "[$symbol ](yellow)"

[lua]
symbol = "󰢱"
format = "[$symbol ](blue)"

[rust]
symbol = ""
format = "[$symbol ](red)"

[java]
symbol = ""
format = "[$symbol ](red)"

[c]
symbol = ""
format = "[$symbol ](blue)"

[golang]
symbol = ""
format = "[$symbol ](blue)"
EOF
}

install_tpm() {
  local tpm_dir="${HOME}/.tmux/plugins/tpm"
  if [[ -d "$tpm_dir/.git" ]]; then
    log "updating tpm in $tpm_dir"
    if ! git -C "$tpm_dir" pull --ff-only; then
      log "warning: could not update tpm, continuing with existing checkout"
    fi
  else
    log "installing tpm into $tpm_dir"
    mkdir -p "$(dirname "$tpm_dir")"
    git clone https://github.com/tmux-plugins/tpm "$tpm_dir"
  fi
}

write_tmux_conf() {
  log "writing ${HOME}/.tmux.conf"
  cat <<'EOF' >"${HOME}/.tmux.conf"
# Tmux config derived from nix-config

set -g default-shell /usr/bin/zsh
set -g default-command "/usr/bin/zsh -l"

set -g base-index 1
setw -g pane-base-index 1
setw -g mode-keys vi
set -g clock-mode-style 24
set -g allow-passthrough on
set -ga update-environment "TERM"
set -ga update-environment "TERM_PROGRAM"

# Plugins
set -g @plugin 'tmux-plugins/tpm'
set -g @plugin 'tmux-plugins/tmux-sensible'
set -g @plugin 'tmux-plugins/tmux-pain-control'
set -g @plugin 'tmux-plugins/tmux-urlview'
set -g @plugin 'tmux-plugins/tmux-prefix-highlight'
set -g @plugin 'dracula/tmux'

set -g @dracula-show-fahrenheit false
set -g @dracula-plugins "battery cpu-usage ram-usage time"
set -g @dracula-show-left-icon session
set -g @dracula-day-month true
set -g @dracula-military-time true
set -g @dracula-battery-label ""

# Initialize TPM
run '~/.tmux/plugins/tpm/tpm'
EOF
}

install_tmux_plugins() {
  local tpm_dir="${HOME}/.tmux/plugins/tpm"
  if [[ -x "$tpm_dir/bin/install_plugins" ]]; then
    log "installing tmux plugins via tpm"
    "$tpm_dir/bin/install_plugins"
  else
    log "skipping tmux plugin install; tpm not found at $tpm_dir"
  fi
}

write_variety_config() {
  local config_dir="${XDG_CONFIG_HOME:-$HOME/.config}/variety"
  local plugin_dir="${config_dir}/pluginconfig/quotes"
  local repo_variety_conf="${SCRIPT_DIR}/dotfiles/variety.conf"
  local repo_quotes="${SCRIPT_DIR}/dotfiles/quotes.txt"
  local scripts_dir="${HOME}/scripts"
  local set_wallpaper_src="${SCRIPT_DIR}/modules/home-manager/scripts/set_wallpaper"

  mkdir -p "$config_dir" "$plugin_dir" "$scripts_dir"

  if [[ -f "$repo_variety_conf" ]]; then
    log "writing ${config_dir}/variety.conf from repo"
    install -m644 "$repo_variety_conf" "${config_dir}/variety.conf"
  else
    log "warning: variety.conf not found at ${repo_variety_conf}; skipping"
  fi

  if [[ -f "$repo_quotes" ]]; then
    log "writing ${plugin_dir}/quotes.txt"
    install -m644 "$repo_quotes" "${plugin_dir}/quotes.txt"
  else
    log "warning: quotes.txt not found at ${repo_quotes}; skipping"
  fi

  if [[ -f "$set_wallpaper_src" ]]; then
    log "installing set_wallpaper script to ${scripts_dir}/set_wallpaper"
    install -m755 "$set_wallpaper_src" "${scripts_dir}/set_wallpaper"
  else
    log "warning: set_wallpaper script not found at ${set_wallpaper_src}; skipping"
  fi
}

write_yt_dlp_config() {
  local config_dir="${XDG_CONFIG_HOME:-$HOME/.config}/yt-dlp"
  local output_dir="$HOME/Video/YouTube"
  mkdir -p "$config_dir" "$output_dir"
  log "writing ${config_dir}/config"
  cat <<'EOF' >"${config_dir}/config"
--output ~/Video/YouTube/%(uploader)s/%(title)s.%(ext)s
--format mp4
EOF
}

install_tat() {
  local bin_dir="${HOME}/.local/bin"
  mkdir -p "$bin_dir"
  local tat_path="${bin_dir}/tat"
  log "writing ${tat_path}"
  cat <<'EOF' >"$tat_path"
#!/bin/sh
#
# Attach or create tmux session named the same as current directory.

path_name="$(basename "$PWD" | tr . -)"
session_name=''${1-$path_name}

not_in_tmux() {
  [ -z "$TMUX" ]
}

session_exists() {
  tmux has-session -t "=$session_name"
}

create_detached_session() {
  (TMUX="" tmux new-session -Ad -s "$session_name")
}

create_if_needed_and_attach() {
  if not_in_tmux; then
    tmux new-session -As "$session_name"
  else
    if ! session_exists; then
      create_detached_session
    fi
    tmux switch-client -t "$session_name"
  fi
}

create_if_needed_and_attach
EOF
  chmod +x "$tat_path"
}

write_vpn_script() {
  local bin_dir="${HOME}/.local/bin"
  mkdir -p "$bin_dir"
  local vpn_path="${bin_dir}/vpn"
  log "writing ${vpn_path}"
  cat <<'EOF' >"$vpn_path"
#!/usr/bin/env bash
set -euo pipefail

DNS_SUFFIX=$(tailscale status --json | jq -r '.MagicDNSSuffix')

EXIT_NODES=$(tailscale status --json | jq -r '.Peer[] | select(.ExitNodeOption==true) | select(.Online==true) | .DNSName' | sed "s/\.$DNS_SUFFIX\.//g")
EXIT_NODES+="
None"
EXIT_NODES=$(echo -e "$EXIT_NODES")

SELECTED=$(tailscale status --json | jq -r '.Peer[] | select(.ExitNode==true) | .DNSName' | sed "s/\.$DNS_SUFFIX\.//g")
if [[ -z "$SELECTED" ]]; then
  SELECTED="None"
fi

EXIT_NODE=$(echo -e "$EXIT_NODES" | gum choose --selected "$SELECTED")
if [[ "$EXIT_NODE" == "None" ]]; then
  sudo tailscale up --exit-node "" --exit-node-allow-lan-access=false
else
  sudo tailscale up --exit-node "$EXIT_NODE" --exit-node-allow-lan-access=true
fi
EOF
  chmod +x "$vpn_path"
}

enable_tailscale_service() {
  if command -v systemctl >/dev/null 2>&1; then
    log "enabling and starting tailscaled.service"
    sudo systemctl enable --now tailscaled.service
  else
    log "systemctl not found; skip enabling tailscaled.service"
  fi
}

write_vless_script() {
  local bin_dir="${HOME}/.local/bin"
  mkdir -p "$bin_dir"
  local vless_path="${bin_dir}/vless"
  log "writing ${vless_path}"
  cat <<'EOF' >"$vless_path"
#!/usr/bin/env bash
set -euo pipefail

SERVICE="vless-sing-box"
CONFIG_PATH="${HOME}/nix-config/secrets/vless/$(hostname).json"

usage() {
  cat <<'HELP'
Usage: vless [up|down|status]

Without arguments an interactive selector is shown when gum is available.
HELP
}

ensure_config() {
  if [[ ! -f "$CONFIG_PATH" ]]; then
    echo "Config not found: $CONFIG_PATH" >&2
    exit 1
  fi
}

choose_action() {
  if [[ $# -gt 1 ]]; then
    usage >&2
    exit 1
  fi

  if [[ $# -eq 1 ]]; then
    echo "$1"
    return
  fi

  if command -v gum >/dev/null 2>&1; then
    gum choose --header="VLESS" up down status
  else
    usage >&2
    exit 1
  fi
}

ensure_config
action=$(choose_action "$@")

case "$action" in
  up)
    sudo systemctl enable --now "$SERVICE"
    ;;
  down)
    sudo systemctl stop "$SERVICE"
    ;;
  status)
    systemctl status "$SERVICE"
    ;;
  *)
    usage >&2
    exit 1
    ;;
esac
EOF
  chmod +x "$vless_path"
}

ensure_vless_docker_firewall() {
  # Allow sing-box redirect port for docker bridges so container traffic can reach the tunnel.
  if ! command -v ufw >/dev/null 2>&1; then
    log "ufw not found; skipping sing-box firewall rule for docker bridges"
    return
  fi

  local port=41935
  local ifaces=()

  if ip link show docker0 >/dev/null 2>&1; then
    ifaces+=("docker0")
  fi

  while IFS=: read -r _ name _; do
    name=${name%%@*}
    if [[ "$name" =~ ^br- ]]; then
      ifaces+=("$name")
    fi
  done < <(ip -o link show 2>/dev/null || true)

  if [[ "${#ifaces[@]}" -eq 0 ]]; then
    log "no docker bridges detected; skipping ufw allow for sing-box"
    return
  fi

  for iface in "${ifaces[@]}"; do
    if sudo ufw status | grep -F " ${port}/tcp" | grep -F "on ${iface}" >/dev/null 2>&1; then
      log "ufw rule for ${port}/tcp on ${iface} already present"
      continue
    fi

    log "allowing ${port}/tcp on ${iface} via ufw for sing-box docker redirect"
    sudo ufw allow in on "${iface}" to any port "${port}" proto tcp comment 'sing-box docker redirect' || true
  done
}

install_vless_service() {
  local service_name="vless-sing-box"
  local config_path="${HOME}/nix-config/secrets/vless/$(hostname).json"
  local runtime_config="/run/${service_name}/config.json"

  if [[ ! -f "$config_path" ]]; then
    log "vless config not found at ${config_path}; skipping service install"
    return
  fi

  log "installing systemd service ${service_name}"
  sudo tee /etc/systemd/system/${service_name}.service >/dev/null <<EOF
[Unit]
Description=VLESS tunnel via sing-box
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
ExecStartPre=/usr/bin/install -Dm0400 ${config_path} ${runtime_config}
ExecStart=/usr/bin/sing-box run --disable-color -c ${runtime_config}
Restart=on-failure
RestartSec=5
CapabilityBoundingSet=CAP_NET_ADMIN CAP_NET_BIND_SERVICE CAP_SETUID CAP_SETGID CAP_DAC_READ_SEARCH
AmbientCapabilities=CAP_NET_ADMIN CAP_NET_BIND_SERVICE CAP_DAC_READ_SEARCH
NoNewPrivileges=true
DeviceAllow=/dev/net/tun rw
RuntimeDirectory=${service_name}
StateDirectory=${service_name}
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
EOF

  sudo systemctl daemon-reload
}

install_radj_service() {
  if ! command -v ryzenadj >/dev/null 2>&1; then
    log "ryzenadj not available; skipping radj service install"
    return
  fi

  local radj_script="/usr/local/lib/radj-loop.sh"
  log "writing ${radj_script}"
  sudo tee "$radj_script" >/dev/null <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

while true; do
  if [[ ! -r /sys/class/power_supply/AC0/online ]]; then
    sleep 60
    continue
  fi

  if [[ "$(cat /sys/class/power_supply/AC0/online)" -eq "1" ]]; then
    ryzenadj --tctl-temp=80 >/dev/null 2>&1 || true
  else
    ryzenadj --tctl-temp=55 >/dev/null 2>&1 || true
  fi

  sleep 60
done
EOF
  sudo chmod 755 "$radj_script"

  log "installing systemd service radj"
  sudo tee /etc/systemd/system/radj.service >/dev/null <<EOF
[Unit]
Description=Ryzen Adj temperature limiter
After=network.target

[Service]
Type=simple
Restart=always
RestartSec=5s
ExecStart=${radj_script}

[Install]
WantedBy=multi-user.target
EOF

  sudo systemctl daemon-reload
  sudo systemctl enable --now radj.service
}

main() {
  local packages=(
    zsh
    zsh-completions
    zsh-autosuggestions
    zsh-syntax-highlighting
    fzf
    starship
    direnv
    gum
    tmux
    git
    git-crypt
    git-lfs
    openssh
    gnupg
    pass
    diff-so-fancy
    urlview
    sing-box
    tailscale
    jq
    telegram-desktop
    moonlight-qt
    otf-monaspace-nerdfonts
    variety
    prismlauncher
    mpv
    yt-dlp
    zoom
    obsidian
    wl-clipboard
    libreoffice-fresh
    antigravity-bin
    neovim
    fd
    ripgrep
    fzy
    rustup
    gcc
    go
    lazygit
    curl
    vale
    proselint
    luaformatter
    prisma-engines
    lua-language-server
    make
    lua51-jsregexp
    nodejs
    npm
    nixfmt-rfc-style
    statix
    emacs-wayland
    cantarell-fonts
    cmake
    libtool
    texlive-bin
    texlive-basic
    texlive-latexextra
    texlive-fontsextra
    texlive-bibtexextra
    graphviz
    sqlite
    libvterm
    ttf-ubuntu-nerd
    ttf-ubuntu-mono-nerd
    ttf-sourcecodepro-nerd
    ttf-hack-nerd
    wordnet
  )

  if [[ "$HOSTNAME_SHORT" == "x13" ]]; then
    packages+=(ryzenadj)
  fi

  ensure_yay

  for pkg in "${packages[@]}"; do
    pacman_install "$pkg"
  done

  local npm_globals=(
    eslint_d
    prettier
    vscode-langservers-extracted
    svelte-language-server
    diagnostic-languageserver
    typescript-language-server
    bash-language-server
    @tailwindcss/language-server
  )

  for npm_pkg in "${npm_globals[@]}"; do
    npm_global_install "$npm_pkg"
  done

  install_tz
  install_tpm
  write_zshrc
  write_starship_config
  write_tmux_conf
  write_variety_config
  write_yt_dlp_config
  install_tat
  write_vpn_script
  enable_tailscale_service
  write_vless_script
  install_vless_service
  ensure_vless_docker_firewall
  configure_openssh
  configure_gpg
  clone_password_store
  if [[ "$HOSTNAME_SHORT" == "x13" ]]; then
    install_radj_service
  else
    log "skipping RyzenAdj setup; hostname is ${HOSTNAME_SHORT}"
  fi
  configure_nix
  install_devenv
  configure_git_defaults
  install_tmux_plugins

  log "done. run 'chsh -s $(command -v zsh)' to make zsh your login shell if needed."
}

main "$@"
