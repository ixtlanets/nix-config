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
  networking.hostName = "x13"; # Define your hostname.

  # Configure keymap in X11
  services = {
    xserver = {
      enable = true;
      dpi = 144;
      videoDrivers = [ "nvidia" ];
      deviceSection = ''Option "TearFree" "true"'';
    };
    asusd.enable = true;
  };

  boot.blacklistedKernelModules = [ "nouveau" ];
# NVIDIA drivers are unfree.
  nixpkgs.config.allowUnfreePredicate = pkg:
    builtins.elem (lib.getName pkg) [
    "nvidia-x11"
    ];
  hardware = {
    opengl = {
      enable = true;
      extraPackages = with pkgs; [
        rocm-opencl-icd
        rocm-opencl-runtime
        amdvlk
      ];
      driSupport = true;
      driSupport32Bit = true;
    };
    nvidia = {
      modesetting.enable = true;
      open = true;
      package = config.boot.kernelPackages.nvidiaPackages.stable;
      prime = {
        allowExternalGpu = true;
        amdgpuBusId = "PCI:56:0:0";
        nvidiaBusId = "PCI:1:0:0";

      };
    };
  };
  system.stateVersion = "22.11"; # Did you read the comment?
}
