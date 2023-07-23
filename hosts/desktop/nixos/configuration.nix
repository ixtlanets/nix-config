# Edit this configuration file to define what should be installed on
# your system.  Help is available in the configuration.nix(5) man page
# and in the NixOS manual (accessible by running ‘nixos-help’).

{ config, pkgs, lib, ... }:

{
  imports =
    [
      # Include the results of the hardware scan.
      ./hardware-configuration.nix
      ../../../modules/nixos/common.nix
    ];

  boot.loader.efi.efiSysMountPoint = lib.mkForce "/boot";
  networking.hostName = "desktop"; # Define your hostname.

  # Configure keymap in X11
  
    services = {
      xserver = {
        enable = true;
        dpi = 144;
      };
    };

  hardware = {
    opengl = {
      enable = true;
      driSupport = true;
      driSupport32Bit = true;
    };
  };
  # NVIDIA drivers are unfree.
  nixpkgs.config.allowUnfreePredicate = pkg:
    builtins.elem (lib.getName pkg) [
      "nvidia-x11"
      "nvidia-settings"
    ];

  # Tell Xorg to use the nvidia driver
  services.xserver.videoDrivers = ["nvidia"];

  hardware.nvidia = {

    # Modesetting is needed for most wayland compositors
    modesetting.enable = true;

    # Use the open source version of the kernel module
    # Only available on driver 515.43.04+
    open = true;

    # Enable the nvidia settings menu
    nvidiaSettings = true;

    # Optionally, you may need to select the appropriate driver version for your specific GPU.
    package = config.boot.kernelPackages.nvidiaPackages.stable;
  };

  programs.steam = {
    enable = true;
    remotePlay.openFirewall = true;
  };
  system.stateVersion = "22.11"; # Did you read the comment?
}
