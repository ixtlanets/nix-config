{ inputs, outputs, lib, config, pkgs, ... }:
{
  home.packages = with pkgs; [
    swayimg
    gnome.adwaita-icon-theme
    swaylock
    swayidle
    rofi-wayland
    grim # screenshot functionality
    slurp # screenshot functionality
    xdg-utils # for opening default programs when clicking links
    glfw-wayland
  ];
  home.sessionVariables = {
    NIXOS_OZONE_WL = "1";
  };
  wayland.windowManager.sway = {
    enable = true;
    systemd.enable = true;
    wrapperFeatures = {
      gtk = true;
    };
    config = {
      terminal = "\${pkgs.foot}/bin/foot";
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
          "${modifier}+Return" = "exec foot";
          "${modifier}+w" = "kill";
          "${modifier}+d" = "exec rofi -show run";
          "${modifier}+Shift+f" = "floating toggle";
        };
    };
    extraConfig = ''
set $laptop eDP-1
bindswitch --reload --locked lid:on output $laptop disable
bindswitch --reload --locked lid:off output $laptop enable
    '';
  };
  programs = {
    waybar = {
      settings = {
        mainBar = {
          modules-left = [ "sway/workspaces" "sway/language" "sway/mode" ];

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
            "format"= " {}";
            "min-length" = 5;
            "tooltip"= false;
          };
          "sway/mode" = {
            "format"= "<span style=\"italic\">{}</span>";
          };
        };
      };
    };
  };
  services.network-manager-applet.enable = true;
  home.file.".config/electron-flags.conf".text = ''
--enable-features=WaylandWindowDecorations
--ozone-platform-hint=auto
  '';
}
