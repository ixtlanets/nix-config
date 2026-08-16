{
  config,
  lib,
  pkgs,
  ...
}:
let
  thermalZone = config.home.sessionVariables.THERMAL_ZONE or null;
  tzList = config.home.sessionVariables.TZ_LIST or "";
  waybarActiveOnlyFix = pkgs.waybar.overrideAttrs (old: {
    postPatch = (old.postPatch or "") + ''
      # `active-only` otherwise keeps every Hyprland workspace declared as
      # persistent, which makes an active-workspace taskbar show all apps.
      substituteInPlace src/modules/hyprland/workspace.cpp \
        --replace-fail '     !this->isPersistent() && \' "" \
        --replace-fail \
          '// if activeOnly is true, hide if not active, persistent, visible or special' \
          '// if activeOnly is true, hide if not active, visible, or special'
    '';
  });
  timezonePicker = pkgs.writeShellScriptBin "timezone-picker" ''
    set -euo pipefail

    configured_tz_list=${lib.escapeShellArg tzList}
    tz_list="''${TZ_LIST:-$configured_tz_list}"
    current="$(${pkgs.systemd}/bin/timedatectl show --property=Timezone --value 2>/dev/null || true)"

    choices=()
    zones=()
    selected=""

    IFS=';' read -r -a pairs <<< "$tz_list"
    for pair in "''${pairs[@]}"; do
      [ -n "$pair" ] || continue

      zone="''${pair%%,*}"
      if [ "$zone" = "$pair" ]; then
        label="$zone"
      else
        label="''${pair#*,}"
      fi

      display="$(printf '%-12s %s' "$label" "$zone")"
      choices+=("$display")
      zones+=("$zone")

      if [ "$zone" = "$current" ]; then
        selected="$display"
      fi
    done

    if [ "''${#choices[@]}" -eq 0 ]; then
      printf 'No time zones configured in TZ_LIST.\n' >&2
      exit 1
    fi

    selected_arg=()
    if [ -n "$selected" ]; then
      selected_arg=(--selected "$selected")
    fi

    choice="$(printf '%s\n' "''${choices[@]}" | ${pkgs.gum}/bin/gum choose "''${selected_arg[@]}" --header "Select time zone")" || exit 0

    selected_zone=""
    for i in "''${!choices[@]}"; do
      if [ "''${choices[$i]}" = "$choice" ]; then
        selected_zone="''${zones[$i]}"
        break
      fi
    done

    if [ -z "$selected_zone" ] || [ "$selected_zone" = "$current" ]; then
      exit 0
    fi

    ${pkgs.systemd}/bin/timedatectl set-timezone "$selected_zone"
    ${pkgs.systemd}/bin/systemctl --user restart waybar || true
  '';
  hyprFocusWindow = pkgs.writeShellApplication {
    name = "hypr-focus-window";
    runtimeInputs = [ pkgs.hyprland ];
    text = ''
      address="''${1:-}"
      button="''${2:-1}"

      # Waybar reports GDK button numbers. Only left click changes focus so
      # middle/right click remain available for future window actions.
      [ "$button" = "1" ] || exit 0

      if [[ ! "$address" =~ ^0x[0-9a-fA-F]+$ ]]; then
        printf 'Invalid Hyprland window address: %s\n' "$address" >&2
        exit 2
      fi

      hyprctl dispatch focuswindow "address:$address" >/dev/null
    '';
  };
in
{
  home.packages = [
    timezonePicker
    hyprFocusWindow
  ];

  programs = {
    waybar = {
      enable = true;
      package = waybarActiveOnlyFix;
      systemd.enable = true;
      settings = {
        mainBar = {
          layer = "top";
          position = "top";
          modules-left = [
            "hyprland/workspaces"
            "hyprland/workspaces#apps"
          ];
          modules-center = [ "clock" ];
          modules-right = [
            "custom/vless"
            "custom/hyprlayout"
            "hyprland/language"
            "pulseaudio"
            "temperature"
            "backlight"
            "battery"
            "tray"
          ];

          "hyprland/workspaces" = {
            "format" = "{id}";
          };
          "hyprland/workspaces#apps" = {
            "active-only" = true;
            "format" = "{windows}";
            "on-scroll-up" = "${pkgs.hyprland}/bin/hyprctl dispatch layoutmsg cycleprev";
            "on-scroll-down" = "${pkgs.hyprland}/bin/hyprctl dispatch layoutmsg cyclenext";
            "workspace-taskbar" = {
              "enable" = true;
              "update-active-window" = true;
              "format" = "{icon}";
              "icon-size" = 14;
              "on-click-window" = "${hyprFocusWindow}/bin/hypr-focus-window {address} {button}";
            };
          };
          "custom/vless" = {
            "exec" =
              "sh -c 'if command -v vless-waybar > /dev/null 2>&1; then exec vless-waybar; else printf '\''{\"text\":\"󱚡\",\"class\":\"inactive\",\"tooltip\":\"VLESS: Inactive\"}\n'\''; fi'";
            "return-type" = "json";
            "format" = "{text}";
            "tooltip" = true;
            "interval" = 5;
            "on-click" = "sh -c 'command -v vless-waybar > /dev/null 2>&1 && exec vless-waybar toggle || true'";
          };
          "custom/hyprlayout" = {
            "exec" = "hypr-layout-waybar";
            "signal" = 8;
            "tooltip" = false;
          };
          "hyprland/language" = {
            "format" = " {}";
            "format-en" = "en";
            "format-ru" = "ру";
          };
          "clock" = {
            "tooltip-format" = "<big>{:%Y %B}</big>\n<tt><span size='larger'>{calendar}</span></tt>";
            "format" = "{:%a, %d %b, %H:%M}";
            "on-click" =
              "${pkgs.wezterm}/bin/wezterm start --class timezone-picker -- ${timezonePicker}/bin/timezone-picker";
            "calendar" = {
              "format" = {
                "months" = "<span color='#f8f8f8'><b>{}</b></span>";
                "days" = "<span color='#d8d8d8'>{}</span>";
                "weekdays" = "<span color='#b8b8b8'>{}</span>";
                "today" = "<span background='#b4befe' color='#181825'><b>{}</b></span>";
              };
            };
          };
          "pulseaudio" = {
            "reverse-scrolling" = 1;
            "format" = "{volume}% {icon} {format_source}";
            "format-bluetooth" = "{volume}% {icon} {format_source}";
            "format-bluetooth-muted" = " {icon} {format_source}";
            "format-muted" = "  {format_source}";
            "format-source" = "{volume}% ";
            "format-source-muted" = "";
            "format-icons" = {
              "headphone" = "";
              "hands-free" = "";
              "headset" = "";
              "phone" = "";
              "portable" = "";
              "car" = "";
              "default" = [
                ""
                ""
                ""
              ];
            };
            "on-click" = "alacritty --class=Wiremix -e wiremix";
            "min-length" = 13;
          };
          temperature = {
            "critical-threshold" = 90;
            "format" = "{icon} {temperatureC}°C";
            "format-icons" = [
              ""
              ""
              ""
              ""
              ""
            ];
            "tooltip" = false;
          }
          // (if thermalZone == null then { } else { "thermal-zone" = builtins.fromJSON thermalZone; });
          backlight = {
            "format" = "{icon} {percent}%";
            "format-icons" = [
              ""
              ""
            ];
            "min-length" = 7;
          };
          "battery" = {
            "format" = "{capacity}% {icon}";
            "format-discharging" = "{capacity}% {icon}";
            "format-charging" = "{capacity}% {icon}";
            "format-plugged" = "";
            "format-icons" = {
              "charging" = [
                "󰢜"
                "󰂆"
                "󰂇"
                "󰂈"
                "󰢝"
                "󰂉"
                "󰢞"
                "󰂊"
                "󰂋"
                "󰂅"
              ];
              "default" = [
                "󰁺"
                "󰁻"
                "󰁼"
                "󰁽"
                "󰁾"
                "󰁿"
                "󰂀"
                "󰂁"
                "󰂂"
                "󰁹"
              ];
            };
            "format-full" = "{capacity}% 󰂅";
            "tooltip-format-discharging" = "{power:>1.0f}W↓ {capacity}%";
            "tooltip-format-charging" = "{power:>1.0f}W↑ {capacity}%";
            "interval" = 5;
            "states" = {
              "warning" = 20;
              "critical" = 10;
            };
            "on-click" = "alacritty --class=Wiremix -e power-profile";
          };
          tray = {
            "icon-size" = 16;
            "spacing" = 4;
          };
        };
      };
      style = builtins.readFile ../../dotfiles/waybar/style.css;
    };

  };
}
