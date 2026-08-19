# Edit this configuration file to define what should be installed on
# your system.  Help is available in the configuration.nix(5) man page
# and in the NixOS manual (accessible by running ‘nixos-help’).

{
  pkgs,
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
    outputs.nixosModules.vless
  ];

  networking.hostName = "x1carbon"; # Define your hostname.

  networking.wireguard.interfaces.wg-hosts = {
    ips = [ "198.18.77.5/32" ];
    privateKeyFile = "/home/nik/nix-config/secrets/wireguard/x1carbon.key";
    peers = [
      {
        publicKey = "Daj7tj5vfs3gIzHWzt9FKadBVrCFf0CyLn0nUc/N5Ug=";
        allowedIPs = [ "198.18.77.0/24" ];
        endpoint = "31.58.85.163:51820";
        persistentKeepalive = 25;
      }
    ];
  };

  services.hardware.bolt.enable = true;

  services.vless = {
    enable = true;
    configPath = "/home/nik/nix-config/secrets/vless/x1carbon.json";
    configUser = "nik";
  };

  hardware = {
    graphics = {
      enable = true;
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
