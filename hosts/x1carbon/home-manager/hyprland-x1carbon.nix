{ pkgs, lib, ... }:
let
  x1-display-profile = pkgs.writeShellScriptBin "x1-display-profile" ''
    set -euo pipefail

    hyprctl_bin="${pkgs.hyprland}/bin/hyprctl"
    jq_bin="${pkgs.jq}/bin/jq"
    socat_bin="${pkgs.socat}/bin/socat"

    apply_profile() {
      local monitors_json external_count edp_disabled

      monitors_json="$($hyprctl_bin -j monitors all)"
      external_count="$(printf '%s' "$monitors_json" | $jq_bin '[.[] | select(.name != "eDP-1" and ((.disabled // false) == false))] | length')"
      edp_disabled="$(printf '%s' "$monitors_json" | $jq_bin -r '(.[] | select(.name == "eDP-1") | (.disabled // false)) // false')"

      if [ "$external_count" -gt 0 ]; then
        if [ "$edp_disabled" != "true" ]; then
          $hyprctl_bin keyword monitor "eDP-1,disable" >/dev/null
        fi
      else
        if [ "$edp_disabled" != "false" ]; then
          $hyprctl_bin keyword monitor "eDP-1,preferred,auto,1.5" >/dev/null
        fi
      fi
    }

    apply_profile

    $socat_bin - "UNIX-CONNECT:$XDG_RUNTIME_DIR/hypr/$HYPRLAND_INSTANCE_SIGNATURE/.socket2.sock" \
      | while read -r line; do
          case "$line" in
            monitoradded*|monitorremoved*)
              apply_profile
              ;;
          esac
        done
  '';
in
{
  home.packages = [
    x1-display-profile
  ];

  wayland.windowManager.hyprland.settings = {
    exec-once = [
      "x1-display-profile"
    ];

    decoration = {
      blur.enabled = lib.mkForce false;
      shadow.enabled = lib.mkForce false;
    };
  };
}
