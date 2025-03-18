{
  inputs,
  outputs,
  lib,
  config,
  pkgs,
  ...
}:
let
  setup-workspace = pkgs.writeShellScriptBin "setup-workspace" ''
    ${pkgs.variety}/bin/variety --next

    # Get list of connected monitors
    monitors=$(${pkgs.hyprland}/bin/hyprctl monitors -j | ${pkgs.jq}/bin/jq -r '.[].name')
    internal_monitor="eDP-1"
    external_monitor=""

    # Find first external monitor
    for monitor in $monitors; do
      if [ "$monitor" != "$internal_monitor" ]; then
        external_monitor=$monitor
        break
      fi
    done

    # Determine target monitor for workspaces 1-5
    target_monitor=$internal_monitor
    if [ -n "$external_monitor" ]; then
      target_monitor=$external_monitor
    fi

    # Set workspace rules
    ${pkgs.hyprland}/bin/hyprctl keyword workspace r1-5, monitor:$target_monitor,persistent:true
    ${pkgs.hyprland}/bin/hyprctl keyword workspace r10, monitor:$internal_monitor,persistent:true

    # Move workspaces to appropriate monitors
    for i in {1..5}; do
      ${pkgs.hyprland}/bin/hyprctl dispatch moveworkspacetomonitor $i $target_monitor
    done
    ${pkgs.hyprland}/bin/hyprctl dispatch moveworkspacetomonitor 10 $internal_monitor
  '';
in
{
  home.packages = [
    setup-workspace
  ];
  programs = {
    waybar = {
      enable = true;
      systemd.enable = true;
      settings = {
        mainBar = {
          layer = "top";
          position = "top";
          modules-center = [ "clock" ];
          modules-right = [
            "custom/workspace-control"
            "pulseaudio"
            "temperature"
            "backlight"
            "battery"
            "keyboard-state"
            "tray"
          ];

          "keyboard-state" = {
            "capslock" = true;
            "format" = "{name} {icon} ";
            "format-icons" = {
              "locked" = " ";
              "unlocked" = "";
            };
          };
          "clock" = {
            "tooltip-format" = "<big>{:%Y %B}</big>\n<tt><small>{calendar}</small></tt>";
            "format" = "{:%a, %d %b, %H:%M}";
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
            "on-click" = "pavucontrol";
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
          };
          backlight = {
            "format" = "{icon} {percent}%";
            "format-icons" = [
              ""
              ""
            ];
            "min-length" = 7;
          };
          "battery" = {
            states = {
              good = 95;
              warning = 20;
              critical = 10;
            };
            format = "{capacity}% {icon}";
            format-charging = "{capacity}% ";
            format-plugged = "";
            tooltip-format = "{time} ({capacity}%)";
            format-alt = "{time} {icon} : {power} W";
            format-full = "";
            format-icons = [
              ""
              ""
              ""
              ""
              ""
            ];
          };
          tray = {
            "icon-size" = 10;
            "spacing" = 4;
          };
          "custom/workspace-control" = {
            "exec" = "${pkgs.writeShellScript "workspace-status" ''
              monitors=$(${pkgs.hyprland}/bin/hyprctl monitors -j | ${pkgs.jq}/bin/jq -r '.[].name')
              count=$(echo "$monitors" | wc -l)
              if [ "$count" -gt 1 ]; then
                    echo '{"text": "", "class": "multi-monitor"}'
                  else
                    echo '{"text": "", "class": "single-monitor"}'
                  fi
            ''}";
            "return-type" = "json";
            "interval" = 2;
            "on-click" = "${setup-workspace}/bin/setup-workspace";
            "tooltip" = false;
          };
        };
      };
      style = builtins.readFile ../../dotfiles/waybar/style.css;
    };

  };
}
