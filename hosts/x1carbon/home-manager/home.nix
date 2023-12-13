# This is your home-manager configuration file
# Use this to configure your home environment (it replaces ~/.config/nixpkgs/home.nix)

{ inputs, outputs, lib, config, pkgs, niknvim, dpi, ... }: 
{
  home.sessionVariables = {
    WIFI_INTERFACE = "wlp4s0";
    HWMON_PATH = "/sys/devices/virtual/thermal/thermal_zone0/hwmon3/temp1_input";
    BACKLIGHT_CARD = "intel_backlight";
  };
  # You can import other home-manager modules here
  imports = [
    ../../../modules/home-manager/starship.nix
    ../../../modules/home-manager/tmux.nix
    ../../../modules/home-manager/common.nix
    ../../../modules/home-manager/services.nix
    ../../../modules/home-manager/emacs.nix
    ../../../modules/home-manager/linux-desktop.nix
    ../../../modules/home-manager/gnome.nix
    ../../../modules/home-manager/sway.nix
    ../../../modules/home-manager/kanshi.nix
    ../../../modules/home-manager/email.nix
    ../../../modules/home-manager/nvim.nix
  ];
  services.kanshi.profiles = {
    mobile = {
      exec = "variety --next";
      outputs = [
        {
          criteria = "eDP-1";
          mode = "1920x1080@60.000Hz";
          scale = 1.5;
        }
      ];
    };
    docked = {
      exec = "variety --next";
      outputs = [
        {
          criteria = "eDP-1";
          mode = "1920x1080@60.000Hz";
          scale = 1.5;
        }
        {
          criteria = "HDMI-A-1";
          mode = "2560x1440@144.000Hz";
          scale = 1.5;
        }
      ];
    };
  };
  wayland.windowManager.sway = {
    config = {
      output = {
        "eDP-1" = {
          mode = "1920x1080@60.000Hz";
          scale = "1.5";
        };
        "HDMI-A-1" = {
          mode = "2560x1440@144.000Hz";
          scale = "1.5";
        };
      };
    };
  };
  programs.waybar.settings.mainbar.output = [
    "eDP-1"
    "HDMI-A-1"
  ];

  dconf.settings = {
    "org/gnome/desktop/interface" = {
      text-scaling-factor = 1.3;
    };
  };

  home = {
    username = "nik";
    homeDirectory = "/home/nik";
  };
  
  home.packages = with pkgs; [
    nvtop
  ];
  xresources.properties = {
    "Xft.dpi" = dpi;
  };

  # https://nixos.wiki/wiki/FAQ/When_do_I_update_stateVersion
  home.stateVersion = "22.11";
}
