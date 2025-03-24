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

  services.ollama = {
    enable = true;
  };
  boot.blacklistedKernelModules = [ "nouveau" ];
  hardware = {
    graphics = {
      enable = true;
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
