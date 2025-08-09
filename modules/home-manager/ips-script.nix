{ pkgs, ... }:
let
  lib = pkgs.lib;
  stdenv = pkgs.stdenv;

  ips-script = pkgs.writeShellApplication {
    name = "ips";
    runtimeInputs =
      (with pkgs; [
        gum
        gawk
        gnugrep
        coreutils
      ])
      ++ lib.optionals stdenv.isLinux (
        with pkgs;
        [
          iproute2
          wl-clipboard
          xclip
          xsel
        ]
      );

    text = ''
      #!/usr/bin/env bash
      set -euo pipefail

      ICON_ETH="󰈀"
      ICON_WIFI="󰖩"
      ICON_LO="󰩟"
      ICON_OTHER="󰒝"

      require() { command -v "$1" >/dev/null 2>&1; }

      get_ips_linux() {
        ip -o -4 addr show \
          | awk '{print $2, $4}' \
          | while read -r ifname cidr; do
              ipaddr="''${cidr%/*}"
              case "$ifname" in
                lo|lo0)                     icon="$ICON_LO"  ;;
                eth*|en*|em*)               icon="$ICON_ETH" ;;
                wl*|wifi*|ath*)             icon="$ICON_WIFI";;
                *)                          icon="$ICON_OTHER" ;;
              esac
              printf "%s %s (%s)\n" "$icon" "$ipaddr" "$ifname"
            done
      }

      get_ips_macos() {
        ifconfig \
          | awk '/flags/{iface=$1; sub(":","",iface)} /inet[[:space:]]/{print iface,$2}' \
          | while read -r ifname ipaddr; do
              case "$ifname" in
                lo|lo0)         icon="$ICON_LO"  ;;
                en*)            icon="$ICON_ETH" ;;
                awdl*|wl*)      icon="$ICON_WIFI";;
                *)              icon="$ICON_OTHER" ;;
              esac
              printf "%s %s (%s)\n" "$icon" "$ipaddr" "$ifname"
            done
      }

      OS="$(uname -s)"
      case "$OS" in
        Linux)  LIST="$(get_ips_linux || true)" ;;
        Darwin) LIST="$(get_ips_macos || true)" ;;
        *)      LIST="" ;;
      esac

      LIST="$(printf "%s\n" "$LIST" \
        | grep -E '([0-9]{1,3}\.){3}[0-9]{1,3}' \
        | grep -v ' 127\.')"

      [ -n "$LIST" ] || { echo "No IPs found." >&2; exit 1; }

      CHOICE="$(printf "%s\n" "$LIST" | gum choose --header "Select IP to copy")"
      [ -n "$CHOICE" ] || exit 0
      IP_ONLY="$(printf "%s" "$CHOICE" | awk '{print $2}')"

      copy_to_clipboard() {
        local text="$1"
        if [ -n "''${WAYLAND_DISPLAY-}" ] && require wl-copy; then printf "%s" "$text" | wl-copy && return 0; fi
        if require xclip;  then printf "%s" "$text" | xclip -selection clipboard && return 0; fi
        if require xsel;   then printf "%s" "$text" | xsel --clipboard --input && return 0; fi
        if require pbcopy; then printf "%s" "$text" | pbcopy && return 0; fi
        if grep -qi microsoft /proc/version 2>/dev/null && command -v clip.exe >/dev/null 2>&1; then printf "%s" "$text" | clip.exe && return 0; fi
        return 1
      }

      if copy_to_clipboard "$IP_ONLY"; then
        gum style --foreground 212 --bold "Copied:" "$IP_ONLY"
      else
        gum style --foreground 203 --bold "No clipboard tool found."
        echo "Selected IP: $IP_ONLY"
      fi
    '';
  };
in
{
  home.packages = [ ips-script ];
}
