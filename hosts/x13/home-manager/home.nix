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
    # If you want to use modules your own flake exports (from modules/home-manager):
    # outputs.homeManagerModules.example

    # Or modules exported from other flakes (such as nix-colors):
    # inputs.nix-colors.homeManagerModules.default

    # You can also split up your configuration and import pieces of it here:
    # ./nvim.nix
    ../../../modules/home-manager/common.nix
  ];

  home.packages = with pkgs; [
    asusctl
    supergfxctl
    nvtop

    gnomeExtensions.supergfxctl-gex
  ];

  # https://nixos.wiki/wiki/FAQ/When_do_I_update_stateVersion
  home.stateVersion = "22.11";
}
