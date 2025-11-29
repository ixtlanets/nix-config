#!/usr/bin/env bash
set -euo pipefail

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

write_zshrc() {
  log "writing ${HOME}/.zshrc"
  cat <<'EOF' >"$HOME/.zshrc"
# Zsh config derived from nix-config (CachyOS/Arch)

export PATH="$HOME/.local/bin:$HOME/go/bin:$PATH"

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

  install_tpm
  write_zshrc
  write_starship_config
  write_tmux_conf
  install_tat
  write_vpn_script
  enable_tailscale_service
  write_vless_script
  install_vless_service
  configure_nix
  install_devenv
  install_tmux_plugins

  log "done. run 'chsh -s $(command -v zsh)' to make zsh your login shell if needed."
}

main "$@"
