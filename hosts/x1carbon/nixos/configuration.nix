# Edit this configuration file to define what should be installed on
# your system.  Help is available in the configuration.nix(5) man page
# and in the NixOS manual (accessible by running ‘nixos-help’).

{ config, pkgs, ... }:

{
  nix.settings.experimental-features = [ "nix-command" "flakes" ];
  imports =
    [
      # Include the results of the hardware scan.
      ./hardware-configuration.nix
      ../../../modules/nixos/common.nix
    ];

  networking.hostName = "x1carbon"; # Define your hostname.

  # Configure keymap in X11
  services = {
    xserver = {
      enable = true;
      dpi = 144;
      videoDrivers = [ "modesetting" ];
    };
  };

  hardware = {
    opengl = {
      enable = true;
      extraPackages = with pkgs; [
        intel-media-driver
        vaapiVdpau
        libvdpau-va-gl
      ];
      driSupport = true;
      driSupport32Bit = true;
    };
  };
  system.stateVersion = "22.11"; # Did you read the comment?
}
