# Edit this configuration file to define what should be installed on
# your system.  Help is available in the configuration.nix(5) man page
# and in the NixOS manual (accessible by running ‘nixos-help’).

{
  config,
  pkgs,
  lib,
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
    ../../../modules/nixos/timezone-picker.nix
    outputs.nixosModules.ollama
    outputs.nixosModules.vless
  ];

  boot.loader.efi.efiSysMountPoint = lib.mkForce "/boot";
  boot.loader.grub.extraEntries = ''
    menuentry "Windows Boot Manager" {
      insmod part_gpt
      insmod fat
      search --no-floppy --fs-uuid --set=root 1A63-5E50
      chainloader /EFI/Microsoft/Boot/bootmgfw.efi
    }
  '';
  networking.hostName = "um790pro"; # Define your hostname.

  networking.wireguard.interfaces.wg-hosts = {
    ips = [ "198.18.77.6/32" ];
    privateKeyFile = "/home/nik/nix-config/secrets/wireguard/um790pro.key";
    peers = [
      {
        publicKey = "Daj7tj5vfs3gIzHWzt9FKadBVrCFf0CyLn0nUc/N5Ug=";
        allowedIPs = [ "198.18.77.0/24" ];
        endpoint = "31.58.85.163:51820";
        persistentKeepalive = 25;
      }
    ];
  };

  # Disable sleep on idle
  services.logind.settings.Login = {
    IdleAction = "ignore";
    HandleSuspendKey = "ignore";
    HandleHibernateKey = "ignore";
    HandleLidSwitch = "ignore";
  };

  programs.ssh.askPassword = pkgs.lib.mkForce "${pkgs.kdePackages.ksshaskpass.out}/bin/ksshaskpass";

  services.hardware.bolt.enable = true;
  services.udev.extraRules = ''
    SUBSYSTEM=="thunderbolt", ATTR{authorized}=="0", ATTR{authorized}="1"
  '';
  services.ollama = {
    enable = true;
  };

  boot.blacklistedKernelModules = [ "nouveau" ];
  services.vless = {
    enable = true;
    configPath = "/home/nik/nix-config/secrets/vless/um790pro.json";
    configUser = "nik";
  };
  hardware = {
    graphics.enable = true;
    nvidia = {
      modesetting.enable = true;
      powerManagement.enable = lib.mkDefault true;
      open = lib.mkDefault false;
      nvidiaSettings = true;
      prime = {
        offload.enable = lib.mkForce false;
        offload.enableOffloadCmd = lib.mkForce false;
      };
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
