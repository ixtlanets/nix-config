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
    ../../../modules/nixos/kde.nix
  ];

  boot.loader.efi.efiSysMountPoint = lib.mkForce "/boot";
  networking.hostName = "zenbook"; # Define your hostname.

  services.ollama = {
    enable = true;
  };

  environment.etc."brave/policies/managed/notifications.json".text = ''
    {
      "DefaultNotificationsSetting": 2
    }
  '';
  services.hardware.bolt.enable = true;
  services = {
    asusd.enable = true;
  };
  boot.blacklistedKernelModules = [ "nouveau" ];
  hardware = {
    graphics = {
      enable = true;
    };
  };
  programs.steam = {
    enable = true;
    remotePlay.openFirewall = true;
    package = pkgs.steam.override {
      extraPkgs = pkgs: [
        pkgs.libglvnd
      ];
    };
  };

  system.stateVersion = "24.11"; # Did you read the comment?
}
