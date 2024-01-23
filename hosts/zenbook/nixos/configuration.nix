# Edit this configuration file to define what should be installed on
# your system.  Help is available in the configuration.nix(5) man page
# and in the NixOS manual (accessible by running ‘nixos-help’).

{ config, pkgs, lib, dpi, ... }:
{
  nix.settings.experimental-features = [ "nix-command" "flakes" ];
  imports =
    [
      # Include the results of the hardware scan.
      ./hardware-configuration.nix
      ../../../modules/nixos/common.nix
    ];

  boot.loader.efi.efiSysMountPoint = lib.mkForce "/boot";
  networking.hostName = "zenbook"; # Define your hostname.

 services.hardware.bolt.enable = true;
 # Configure keymap in X11
  services = {
    xserver = {
      enable = true;
      dpi = dpi;
      videoDrivers = [ "nvidia" ];
      deviceSection = ''Option "TearFree" "true"'';
    };

    autorandr = {
      enable = true;
      hooks.postswitch = {
        "polybar" = ''
          killall polybar
          for m in $(xrandr --query | grep " connected" | cut -d" " -f1); do
            MONITOR=$m polybar --reload mainbar-i3 &
              done
              variety --next
              '';
      };
      profiles = {
        "mobile" = {
          fingerprint = {
            eDP-1 = "00ffffffffffff004c836d4100000000191f0104b51f1478020cf1ae523cb9230c50540000000101010101010101010101010101010139ff405cb00820701420080438c31000001b39ff405cb00848771420080438c31000001b0000000f00ff0a78ff0a3c28800200000000000000fe0041544e413435414630312d3020017202030f00e3058000e606050174600700000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000b7";
          };
          config = {
            eDP-1 = {
              enable = true;
              primary = true;
              mode = "2880x1800";
              rate = "60.00";
              dpi = dpi;
            };
          };
        };
        "docked" = {
          fingerprint = {
            HDMI-1 = "00ffffffffffff0061a9012701000000141e0103803c2178afebc5ad4f45af270c5054a5cb0081c081809500a9c0b300d1c0a9c00101565e00a0a0a029503020350055502100001a000000ff0032373537353030303130313033000000fd0030901ef03c010a202020202020000000fc004d69204d6f6e69746f720a202001ec020346f34d0102030405901213141f4d5c3f23090707830100006a030c001000387820000067d85dc40178c0006d1a000002013090ed0000000000e305e301e6060701605000fd8180a070381f402040450055502100001ef5bd00a0a0a032502040450055502100001e9ee00078a0a032501040350055502100001e00000053";
            eDP-1 = "00ffffffffffff004c836d4100000000191f0104b51f1478020cf1ae523cb9230c50540000000101010101010101010101010101010139ff405cb00820701420080438c31000001b39ff405cb00848771420080438c31000001b0000000f00ff0a78ff0a3c28800200000000000000fe0041544e413435414630312d3020017202030f00e3058000e606050174600700000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000b7";
          };
          config = {
            eDP-1 = {
              enable = true;
              primary = false;
              mode = "2880x1800";
              rate = "120.00";
              position = "0x0";
              dpi = dpi;
            };
            HDMI-1 = { 
              enable = true;
              primary = true;
              mode = "2560x1440";
              rate = "144.0";
              position = "2880x0";
              dpi = 144;
            };
          };
        };
        "dockedclamshell" = {
          fingerprint = {
            HDMI-1 = "00ffffffffffff0061a9012701000000141e0103803c2178afebc5ad4f45af270c5054a5cb0081c081809500a9c0b300d1c0a9c00101565e00a0a0a029503020350055502100001a000000ff0032373537353030303130313033000000fd0030901ef03c010a202020202020000000fc004d69204d6f6e69746f720a202001ec020346f34d0102030405901213141f4d5c3f23090707830100006a030c001000387820000067d85dc40178c0006d1a000002013090ed0000000000e305e301e6060701605000fd8180a070381f402040450055502100001ef5bd00a0a0a032502040450055502100001e9ee00078a0a032501040350055502100001e00000053";
          };
          config = {
            HDMI-1 = {
              enable = true;
              primary = true;
              mode = "2560x1440";
              rate = "144.0";
              dpi = 144;
            };
          };
        };
      };
    };
    asusd.enable = true;
  };
  boot.blacklistedKernelModules = [ "nouveau" ];
  hardware = {
    opengl = {
      enable = true;
      driSupport = true;
      driSupport32Bit = true;
    };
    nvidia = {
      modesetting.enable = true;
    };
  };
  programs.steam = {
    enable = true;
    remotePlay.openFirewall = true;
  };
  programs.hyprland.enable = true;
  system.stateVersion = "22.11"; # Did you read the comment?
}
