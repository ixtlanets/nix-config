# Edit this configuration file to define what should be installed on
# your system.  Help is available in the configuration.nix(5) man page
# and in the NixOS manual (accessible by running ‘nixos-help’).

{
  inputs,
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
    ./power.nix
    ../../../modules/nixos/common.nix
  ];

  boot.loader.efi.efiSysMountPoint = lib.mkForce "/boot";
  networking.hostName = "x13"; # Define your hostname.
  services.hardware.bolt.enable = true;
  services = {
    xserver = {
      enable = true;
      dpi = dpi;
      displayManager.gdm.enable = true;
      desktopManager.gnome.enable = true;
    };
  };

  services.ollama = {
    enable = true;
  };
  boot.blacklistedKernelModules = [ "nouveau" ];
  boot.kernelParams = [
    "amdgpu.gpu_recovery=1"
    "mem_sleep_default=deep"
    "pcie_aspm.policy=powersupersave"
  ];

  services = {
    asusd = {
      enable = true;
      enableUserService = true;
    };

    supergfxd.enable = true;

    udev = {
      extraHwdb = ''
        # Fixes mic mute button
        evdev:name:*:dmi:bvn*:bvr*:bd*:svnASUS*:pn*:*
        KEYBOARD_KEY_ff31007c=f20
      '';
    };
  };

  #flow devices are 2 in 1 laptops
  hardware.sensor.iio.enable = true;

  hardware = {
    graphics = {
      enable = true;
      extraPackages = with pkgs; [
        intel-media-driver
        vaapiVdpau
        libvdpau-va-gl
      ];
    };
  };
  hardware.cpu.amd.ryzen-smu.enable = true; # ryzenadj need it to read info from CPU
  programs.steam = {
    enable = true;
    remotePlay.openFirewall = true;
  };
  environment.systemPackages = [
    pkgs.xf86_input_wacom
    pkgs.ryzenadj # precisely adjust power settings on Ryzen CPUs
  ];
  system.stateVersion = "24.11"; # Did you read the comment?
}
