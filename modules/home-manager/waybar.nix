{
  inputs,
  outputs,
  lib,
  config,
  pkgs,
  ...
}:
{
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
          battery = {
            "states" = {
              "warning" = 25;
              "critical" = 10;
            };
            "format" = "{icon} {capacity}%";
            "format-alt" = "{icon} {time}: {power} W";
            "format-icons" = [
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
        };
      };
      style = builtins.readFile ../../dotfiles/waybar/style.css;
    };

  };
}
