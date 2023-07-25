# Edit this configuration file to define what should be installed on
# your system.  Help is available in the configuration.nix(5) man page
# and in the NixOS manual (accessible by running ‘nixos-help’).

{ config, pkgs, lib, ... }:

{
  nix.settings.experimental-features = [ "nix-command" "flakes" ];
  imports =
    [
      # Include the results of the hardware scan.
      ./hardware-configuration.nix
      ../../../modules/nixos/common.nix
    ];

  boot.loader.efi.efiSysMountPoint = lib.mkForce "/boot";
  networking.hostName = "vmmac"; # Define your hostname.

  # Configure keymap in X11
  services = {
    xserver = {
      dpi = 192;
    };
  };

  environment.systemPackages = with pkgs; [
    open-vm-tools
  ];
  system.stateVersion = "22.11"; # Did you read the comment?
}
