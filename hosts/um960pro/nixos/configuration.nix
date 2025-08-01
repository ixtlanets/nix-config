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
    ../../../modules/nixos/gnome.nix
  ];

  boot.loader.efi.efiSysMountPoint = lib.mkForce "/boot";
  networking.hostName = "um790pro"; # Define your hostname.

  # Disable sleep on idle
  services.logind.extraConfig = ''
    IdleAction=ignore
    HandleSuspendKey=ignore
    HandleHibernateKey=ignore
    HandleLidSwitch=ignore
  '';

  programs.ssh.askPassword = pkgs.lib.mkForce "${pkgs.kdePackages.ksshaskpass.out}/bin/ksshaskpass";

  services.hardware.bolt.enable = true;
  services.ollama = {
    enable = true;
    acceleration = "rocm";
  };

  boot.blacklistedKernelModules = [ "nouveau" ];
  hardware = {
    graphics = {
      enable = true;
    };
  };
  programs.steam = {
    enable = true;
    remotePlay.openFirewall = true;
  };
  system.stateVersion = "24.11"; # Did you read the comment?
}
