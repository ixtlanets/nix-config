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
    ../../../modules/nixos/hyprland.nix
    ../../../modules/nixos/nautilus.nix
  ];

  networking.hostName = "x1extreme"; # Define your hostname.

  # Configure keymap in X11
  services = {
    xserver = {
      enable = true;
      dpi = dpi;
      displayManager.gdm.enable = true;
      desktopManager.gnome.enable = true;
      videoDrivers = [ "nvidia" ];
    };
  };

  boot.blacklistedKernelModules = [ "nouveau" ];
  # NVIDIA drivers are unfree.
  nixpkgs.config.allowUnfreePredicate =
    pkg:
    builtins.elem (lib.getName pkg) [
      "nvidia-x11"
    ];
  hardware = {
    graphics = {
      enable = true;
      extraPackages = with pkgs; [
        intel-media-driver
        vaapiVdpau
        libvdpau-va-gl
      ];
    };
    nvidia = {
      modesetting.enable = true;
      open = true;
      package = config.boot.kernelPackages.nvidiaPackages.stable;
      prime = {
        allowExternalGpu = true;
        intelBusId = "PCI:0:2:0";
        nvidiaBusId = "PCI:9:0:0";

      };
    };
  };
  system.stateVersion = "24.11"; # Did you read the comment?
}
