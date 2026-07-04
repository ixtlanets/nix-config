# Edit this configuration file to define what should be installed on
# your system.  Help is available in the configuration.nix(5) man page
# and in the NixOS manual (accessible by running ‘nixos-help’).

{
  pkgs,
  lib,
  dpi,
  outputs,
  ...
}:
let
  steamScale = toString (dpi / 96.0);
in
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
  networking.firewall.interfaces = {
    tailscale0.allowedTCPPorts = [ 4096 ];
    wlo1.allowedTCPPorts = [ 4096 ];
  };
  time.timeZone = lib.mkForce null;

  services.logind.settings.Login.HandleLidSwitchExternalPower = "ignore";

  programs.ssh.askPassword = lib.mkForce "${pkgs.kdePackages.ksshaskpass.out}/bin/ksshaskpass";

  systemd.services.lid-ac-inhibitor = {
    description = "Ignore lid switch while external power is connected";
    after = [ "systemd-logind.service" ];
    wantedBy = [ "multi-user.target" ];
    path = with pkgs; [
      coreutils
      systemd
    ];
    script = ''
      set -eu

      inhibitor_pid=""

      on_external_power() {
        for supply in /sys/class/power_supply/*; do
          if [ -r "$supply/type" ] \
            && [ "$(cat "$supply/type")" = "Mains" ] \
            && [ -r "$supply/online" ] \
            && [ "$(cat "$supply/online")" = "1" ]; then
            return 0
          fi
        done

        return 1
      }

      start_inhibitor() {
        if [ -n "$inhibitor_pid" ] && kill -0 "$inhibitor_pid" 2>/dev/null; then
          return
        fi

        systemd-inhibit \
          --what=handle-lid-switch \
          --why="External power connected" \
          --mode=block \
          sleep infinity &
        inhibitor_pid="$!"
      }

      stop_inhibitor() {
        if [ -n "$inhibitor_pid" ] && kill -0 "$inhibitor_pid" 2>/dev/null; then
          kill "$inhibitor_pid"
          wait "$inhibitor_pid" 2>/dev/null || true
        fi

        inhibitor_pid=""
      }

      trap stop_inhibitor INT TERM EXIT

      while true; do
        if on_external_power; then
          start_inhibitor
        else
          stop_inhibitor
        fi

        sleep 5
      done
    '';
    serviceConfig = {
      Restart = "always";
      RestartSec = "5s";
    };
  };

  networking.wireguard.interfaces.wg-hosts = {
    ips = [ "198.18.77.3/32" ];
    privateKeyFile = "/home/nik/nix-config/secrets/wireguard/zenbook.key";
    peers = [
      {
        publicKey = "Daj7tj5vfs3gIzHWzt9FKadBVrCFf0CyLn0nUc/N5Ug=";
        allowedIPs = [ "198.18.77.0/24" ];
        endpoint = "31.58.85.163:51820";
        persistentKeepalive = 25;
      }
    ];
  };

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
      extraEnv = {
        STEAM_FORCE_DESKTOPUI_SCALING = steamScale;
      };
      extraPkgs = pkgs: [
        pkgs.libglvnd
      ];
    };
  };

  system.stateVersion = "24.11"; # Did you read the comment?
}
