{ inputs, outputs, lib, config, pkgs, dpi, ... }: 
let
  DPI = builtins.toString dpi;
  polybar_height = (builtins.toString(dpi * 0.2));
in
{
  home.packages = with pkgs; [
    feh
    rofi
    maim # screenshot tool
  ];
  home.file.".config/i3/config".text = builtins.readFile ../../dotfiles/i3;
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
    extraConfig = builtins.replaceStrings ["DPI" "HEIGHT"] [DPI polybar_height] (builtins.readFile ../../dotfiles/polybar.ini);
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
  services.network-manager-applet.enable = true;
}
