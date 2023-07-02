# This is your home-manager configuration file
# Use this to configure your home environment (it replaces ~/.config/nixpkgs/home.nix)

{ inputs, outputs, lib, config, pkgs, niknvim, ... }: 
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
    ../../../modules/home-manager/sway.nix
  ];

  home = {
    username = "nik";
    homeDirectory = "/home/nik";
  };
  
  home.packages = with pkgs; [
    nvtop
  ];
  xresources.properties = {
    "Xft.dpi" = 144;
  };

  # https://nixos.wiki/wiki/FAQ/When_do_I_update_stateVersion
  home.stateVersion = "22.11";
}
