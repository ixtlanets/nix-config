# This is your home-manager configuration file
# Use this to configure your home environment (it replaces ~/.config/nixpkgs/home.nix)

{ inputs, outputs, lib, config, pkgs, niknvim, dpi, ... }: 
{
  home.sessionVariables = {
    WIFI_INTERFACE = "wlo1";
    HWMON_PATH = "/sys/devices/platform/coretemp.0/hwmon/hwmon5/temp1_input";
    THERMAL_ZONE = "10";
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
    ../../../modules/home-manager/i3.nix
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
    "Xft.dpi" = dpi;
  };


  # https://nixos.wiki/wiki/FAQ/When_do_I_update_stateVersion
  home.stateVersion = "22.11";
}