{
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
             "tooltip-format" = "<big>{:%Y %B}</big>\n<tt><span size='larger'>{calendar}</span></tt>";
             "format" = "{:%a, %d %b, %H:%M}";
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
            "icon-size" = 10;
            "spacing" = 4;
          };
        };
      };
      style = builtins.readFile ../../dotfiles/waybar/style.css;
    };

  };
}
