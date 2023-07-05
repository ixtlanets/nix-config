# This is your home-manager configuration file
# Use this to configure your home environment (it replaces ~/.config/nixpkgs/home.nix)

{ inputs, outputs, lib, config, pkgs, ... }:
{
  home.sessionVariables = {
    WIFI_INTERFACE = "wlp6s0";
    HWMON_PATH = "/sys/devices/virtual/thermal/thermal_zone0/hwmon5/temp1_input";
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
    ../../../modules/home-manager/sway.nix
    ../../../modules/home-manager/kanshi.nix
  ];
  services.kanshi.profiles = {
    mobile = {
      exec = "variety --next";
      outputs = [
        {
          criteria = "eDP-1";
          mode = "1920x1200@60.000Hz";
          scale = 1.5;
        }
      ];
    };
    docked = {
      exec = "variety --next";
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
  };
  wayland.windowManager.sway = {
    config = {
      output = {
        "eDP-1" = {
          mode = "1920x1080@60.000Hz";
          scale = "1.5";
        };
        "DP-1" = {
          mode = "2560x1440@144.000Hz";
          scale = "1.5";
        };
      };
    };
  };
  programs.waybar.settings.mainbar.output = [
    "eDP-1"
    "DP-1"
  ];

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
    "Xft.dpi" = 144;
  };

  # https://nixos.wiki/wiki/FAQ/When_do_I_update_stateVersion
  home.stateVersion = "22.11";
}
