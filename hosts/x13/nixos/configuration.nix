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

  boot.loader.efi.efiSysMountPoint = lib.mkForce "/boot";
  networking.hostName = "x13"; # Define your hostname.

  # Configure keymap in X11
  
    services = {
      xserver = {
        enable = true;
        dpi = dpi;
        videoDrivers = [ "nvidia" ];
        deviceSection = ''Option "TearFree" "true"'';
      };
      asusd.enable = true;
    };

  boot.blacklistedKernelModules = [ "nouveau" ];
  hardware = {
    opengl = {
      enable = true;
      driSupport = true;
      driSupport32Bit = true;
    };
    nvidia = {
      modesetting.enable = true;
    };
  };
  programs.steam = {
    enable = true;
    remotePlay.openFirewall = true;
  };
  system.stateVersion = "22.11"; # Did you read the comment?
}
