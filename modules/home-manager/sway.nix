{ inputs, outputs, lib, config, pkgs, ... }:
{

  home.packages = with pkgs; [
    liberation_ttf
    font-awesome
  ];
  wayland.windowManager.sway = {
    enable = true;
    systemd.enable = true;
    config = {
      terminal = "alacritty";
      modifier = "Mod4";
      bars = [];
      input = {
        "type:keyboard" = {
          xkb_layout = "us,ru";
          xkb_options = "grp:win_space_toggle";
          repeat_delay = "250";
          repeat_rate = "30";
        };
        "type:touchpad" = {
          tap = "enabled";
          natural_scroll = "enabled";
        };
      };
      fonts = {
        names = [ "Hack Nerd Font Mono" ];
        size = 11.0;
      };
      startup = [
      { command = "variety"; always = true; }
      { command = "systemctl --user restart waybar"; always = true; }
      ];
      window = {
        border = 2;
      };
      output = {
        "eDP-1" = {
          mode = "3120x2080@90.000Hz";
          scale = "3";
        };
        "DP-1" = {
          mode = "2560x1440@144.000Hz";
          scale = "2";
        };
      };
      keybindings =
        let
        modifier = config.wayland.windowManager.sway.config.modifier;
      in
        lib.mkOptionDefault {
          "XF86MonBrightnessUp" = "exec light -A 10";
          "XF86MonBrightnessDown" = "exec light -U 10";
          "XF86AudioLowerVolume" = "exec wpctl set-volume @DEFAULT_AUDIO_SINK@ 0.1-";
          "XF86AudioRaiseVolume" = "exec wpctl set-volume @DEFAULT_AUDIO_SINK@ 0.1+";
          "XF86AudioMute" = "exec wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle";
          "XF86AudioMicMute" = "exec wpctl set-mute @DEFAULT_AUDIO_SOURCE@ toggle";
          "${modifier}+Return" = "exec alacritty";
          "${modifier}+w" = "kill";
          "${modifier}+d" = "exec rofi -show run";
        };
    };
  };
  programs = {
    waybar = {
      enable = true;
      systemd.enable = true;
      settings = {
        mainBar = {
          layer = "top";
          position = "top";
          height = 12;
          output = [
            "eDP-1"
            "DP-1"
          ];
          modules-left = [ "sway/workspaces" "sway/language" "sway/mode" ];
          modules-center = [ "clock" ];
          modules-right = ["pulseaudio" "temperature" "backlight" "battery" "keyboard-state" "tray"];

          "sway/workspaces" = {
            disable-scroll = true;
            all-outputs = true;
            "persistent_workspaces"= {
              "1"= [];
              "2"= [];
              "3"= [];
              "4"= [];
            };
          };
          "sway/language" = {
            "format"= "{} ";
            "min-length" = 5;
            "tooltip"= false;
          };
          "keyboard-state" = {
            "capslock" = true;
            "format" = "{name} {icon} ";
            "format-icons" = {
              "locked" = " ";
              "unlocked" = "";
            };
          };
          "sway/mode" = {
            "format"= "<span style=\"italic\">{}</span>";
          };

          "clock"= {
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
              "portable"= "";
              "car" = "";
              "default" = ["" "" ""];
            };
            "on-click" = "pavucontrol";
            "min-length" = 13;
          };
        };
        "temperature" = {
          "critical-threshold" = 90;
          "format" = "{temperatureC}°C {icon}";
          "format-icons" = [""  ""  ""  ""  ""];
          "tooltip" = false;
        };

        "backlight" = {
          "format" = "{percent}% {icon}";
          "format-icons" = ["" ""];
          "min-length" = 7;
        };

        "battery" = {
          "states" = {
            "warning" = 25;
            "critical" = 10;
          };
          "format" = "{capacity}% {icon}";
          "format-charging" = "{capacity}% ";
          "format-plugged" = "{capacity}% ";
          "format-alt" = "{time} {icon}";
          "format-icons" = ["" "" "" "" ""];
        };

        "tray" = {
          "icon-size" = 12;
          "spacing" = 5;
        };
      };
      style = builtins.readFile ../../dotfiles/waybar/style.css;
    };
  };
}
