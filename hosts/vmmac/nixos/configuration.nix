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
      ../../../modules/nixos/vmware-guest.nix
      ../../../modules/nixos/common.nix
    ];

  # Setup qemu so we can run x86_64 binaries
  boot.binfmt.emulatedSystems = ["x86_64-linux"];

  # Disable the default module and import our override. We have
  # customizations to make this work on aarch64.
  disabledModules = [ "virtualisation/vmware-guest.nix" ];


  # Lots of stuff that uses aarch64 that claims doesn't work, but actually works.
  nixpkgs.config.allowUnfree = true;
  nixpkgs.config.allowUnsupportedSystem = true;

  # This works through our custom module imported above
  virtualisation.vmware.guest.enable = true;

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
