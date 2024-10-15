# This is your home-manager configuration file
# Use this to configure your home environment (it replaces ~/.config/nixpkgs/home.nix)

{ inputs, outputs, lib, config, pkgs, dpi, ... }:
{
  home.sessionVariables = {
    WIFI_INTERFACE = "wlp6s0";
    HWMON_PATH = "/sys/devices/virtual/thermal/thermal_zone0/hwmon5/temp1_input";
    THERMAL_ZONE = "0";
    BACKLIGHT_CARD = "amdgpu_bl0";
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
    ../../../modules/home-manager/hyprland.nix
    ../../../modules/home-manager/waybar.nix
    ../../../modules/home-manager/foot.nix
    ../../../modules/home-manager/email.nix
    ../../../modules/home-manager/nvim.nix
  ];

  wayland.windowManager.hyprland.settings = {
    monitor = [
      "eDP-1,1920x1200@60.000Hz,auto,1.5"
        "HDMI-A-1,2560x1440@144.000Hz,auto,1.5"
        "DP-1,3840x2560@60.000Hz,auto,2.0"
        "DP-2,3840x2560@60.000Hz,auto,2.0"
    ];
  };
  services.kanshi.profiles = {
    mobile = {
      exec = "${pkgs.variety}/bin/variety --next";
      outputs = [
        {
          criteria = "eDP-1";
          mode = "1920x1200@60.000Hz";
          scale = 1.5;
        }
      ];
    };
    dockedHome = {
      exec = "${pkgs.variety}/bin/variety --next";
      outputs = [
        {
          criteria = "eDP-1";
          mode = "1920x1200@60.000Hz";
          scale = 1.5;
        }
        {
          criteria = "DP-1";
          mode = "2560x1440@144.000Hz";
          scale = 1.5;
        }
      ];
    };
    dockedSG = {
      exec = "${pkgs.variety}/bin/variety --next";
      outputs = [
        {
          criteria = "eDP-1";
          mode = "1920x1200@60.000Hz";
          scale = 1.5;
        }
        {
          criteria = "DP-1";
          mode = "3840x2560@60.000Hz";
          scale = 2.0;
        }
      ];
    };

  };
  programs.waybar.settings.mainbar.output = [
    "eDP-1"
    "DP-1"
    "DP-2"
  ];
  dconf.settings = {
    "org/gnome/desktop/interface" = {
      text-scaling-factor = 1.0;
    };
  };
  home = {
    username = "nik";
    homeDirectory = "/home/nik";
  };

  home.packages = with pkgs; [
    asusctl
    supergfxctl
    nvtop

    gnomeExtensions.supergfxctl-gex
  ];

  xresources.properties = {
    "Xft.dpi" = dpi;
  };

  # https://nixos.wiki/wiki/FAQ/When_do_I_update_stateVersion
  home.stateVersion = "24.11";
}
