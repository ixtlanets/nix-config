# Edit this configuration file to define what should be installed on
# your system.  Help is available in the configuration.nix(5) man page
# and in the NixOS manual (accessible by running ‘nixos-help’).

{ config, pkgs, lib, dpi, ... }:
{

  nix.settings.experimental-features = [ "nix-command" "flakes" ];
  imports =
    [
      # Include the results of the hardware scan.
      ./hardware-configuration.nix
      ../../../modules/nixos/common.nix
    ];

  networking.hostName = "x1carbon"; # Define your hostname.

  services = {
    xserver = {
      enable = true;
      dpi = dpi;
      displayManager.gdm.enable = true;
      desktopManager.gnome.enable = true;
    };
  };


  services.hardware.bolt.enable = true;
# NVIDIA drivers are unfree.
  nixpkgs.config.allowUnfreePredicate = pkg:
    builtins.elem (lib.getName pkg) [
    "nvidia-x11"
    "nvidia-settings"
  ];
  hardware = {
    opengl = {
      enable = true;
      driSupport = true;
      driSupport32Bit = true;
    };
  };

  programs.steam = {
    enable = true;
    remotePlay.openFirewall = true;
  };
  programs.hyprland.enable = true;
  system.stateVersion = "22.11"; # Did you read the comment?
}
