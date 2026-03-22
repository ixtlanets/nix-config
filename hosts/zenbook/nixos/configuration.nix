# Edit this configuration file to define what should be installed on
# your system.  Help is available in the configuration.nix(5) man page
# and in the NixOS manual (accessible by running ‘nixos-help’).

{
  config,
  pkgs,
  lib,
  dpi,
  outputs,
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
    outputs.nixosModules.ollama
    outputs.nixosModules.vless
  ];

  boot.loader.efi.efiSysMountPoint = lib.mkForce "/boot";
  networking.hostName = "zenbook"; # Define your hostname.

  swapDevices = [
    {
      device = "/var/lib/swapfile";
      size = 8 * 1024; # 8 GB
    }
  ];

  services.ollama = {
    enable = true;
    package = pkgs.ollama-cuda;
  };

  environment.etc."brave/policies/managed/notifications.json".text = ''
    {
      "DefaultNotificationsSetting": 2
    }
  '';
  services.hardware.bolt.enable = true;
  services.udev.extraRules = ''
    SUBSYSTEM=="thunderbolt", ATTR{authorized}=="0", ATTR{authorized}="1"
  '';
  services = {
    asusd.enable = true;
    supergfxd.enable = true;
  };
  services.vless = {
    enable = true;
    configPath = "/home/nik/nix-config/secrets/vless/zenbook.json";
    configUser = "nik";
  };
  boot.blacklistedKernelModules = [ "nouveau" ];
  boot.kernel.sysctl = {
    "vm.page-cluster" = 0;
    "vm.swappiness" = 80;
  };
  zramSwap = {
    enable = true;
    algorithm = "zstd";
    memoryPercent = 50;
    priority = 100;
  };
  hardware = {
    graphics = {
      enable = true;
      extraPackages = with pkgs; [
        vulkan-loader
      ];
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
