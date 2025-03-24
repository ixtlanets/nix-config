# Edit this configuration file to define what should be installed on
# your system.  Help is available in the configuration.nix(5) man page
# and in the NixOS manual (accessible by running ‘nixos-help’).

{
  config,
  pkgs,
  lib,
  dpi,
  ...
}:
{

  nix.settings.experimental-features = [
    "nix-command"
    "flakes"
  ];
  imports = [
    # Include the results of the hardware scan.
    ./hardware-configuration.nix
    ../../../modules/nixos/common.nix
  ];

  networking.hostName = "x1carbon"; # Define your hostname.

  services.hardware.bolt.enable = true;

  hardware = {
    graphics = {
      enable = true;
    };
  };

  programs.steam = {
    enable = true;
    remotePlay.openFirewall = true;
  };
  system.stateVersion = "24.11"; # Did you read the comment?
}
