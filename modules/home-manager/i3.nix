{ inputs, outputs, lib, config, pkgs, ... }: 
{
  home.packages = with pkgs; [
    feh
    rofi
    maim # screenshot tool
  ];
  home.file.".config/i3/config".text = builtins.readFile ../../dotfiles/i3;
  programs = {
    i3status = {
      enable = true;

      general = {
        colors = true;
        color_good = "#8C9440";
        color_bad = "#A54242";
        color_degraded = "#DE935F";
      };

      modules = {
        ipv6.enable = false;
        "wireless _first_".enable = true;
        "battery all".enable = true;
        "volume master" = {
          position = 1;
          settings = {
            format = "♪ %volume";
            format_muted = "♪ muted (%volume)";
            device = "pulse:1";
          };
        };
      };
    };
  };
  services.picom = {
    enable = true;
    shadow = true;
    backend = "glx";
    inactiveOpacity = 0.8;
    vSync = true;
  };
  services.polybar = {
    enable = true;
    package = pkgs.polybarFull;
    script = "polybar mainbar-i3 &";
    config = ../../dotfiles/polybar.ini;
  };
  services.dunst = {
    enable = true;
    settings = {
      global = {
        width = 300;
        height = 300;
        offset = "10x10";
        origin = "top-right";
        transparency = 10;
        frame_color = "#8AADF4";
        separator_color = "frame";
        font = "Hack Nerd Font 10";
      };
      urgency_low = {
        background = "#24273A";
        foreground = "#CAD3F5";
        timeout = 1;
      };

      urgency_normal = {
        background = "#24273A";
        foreground = "#CAD3F5";
        timeout = 3;
      };

      urgency_critical = {
        background = "#24273A";
        foreground = "#CAD3F5";
        frame_color = "#F5A97F";
        timeout = 3;
      };
    };
  };
}
