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
  networking.hostName = "matebook"; # Define your hostname.

  # Configure keymap in X11
  services = {
    xserver = {
      dpi = 144;
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
              eDP-1 = "00ffffffffffff0051b8221430314b3018200104b51e1478070f95ae5243b0260f505400000001010101010101010101010101010101f4f530b4c0202880302086042cc810000018000000fd00305abfbf3f010a20202020202000000010000a20202020202020202020202000000010000a202020202020202020202020023802030f00e3058000e60605016f6f2200000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000927013790000030128f3f500042f0cb3002f001f001f084b0417000500f3f500042f0cb3002f001f001f08660717000500000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000b690";
            };
            config = {
              eDP-1 = {
                enable = true;
                primary = true;
                mode = "1920x1200";
                rate = "59.88";
              };
            };
          };
          "docked" = {
            fingerprint = {
              DP-1 = "00ffffffffffff0061a9012701000000141e0103803c2178afebc5ad4f45af270c5054a5cb0081c081809500a9c0b300d1c0a9c00101565e00a0a0a029503020350055502100001a000000ff0032373537353030303130313033000000fd0030901ef03c010a202020202020000000fc004d69204d6f6e69746f720a202001ec020346f34d0102030405901213141f4d5c3f23090707830100006a030c001000387820000067d85dc40178c0006d1a000002013090ed0000000000e3050301e6060000000000fd8180a070381f402040450055502100001ef5bd00a0a0a032502040450055502100001e9ee00078a0a032501040350055502100001e000000eb";
              eDP-1 = "00ffffffffffff0051b8221430314b3018200104b51e1478070f95ae5243b0260f505400000001010101010101010101010101010101f4f530b4c0202880302086042cc810000018000000fd00305abfbf3f010a20202020202000000010000a20202020202020202020202000000010000a202020202020202020202020023802030f00e3058000e60605016f6f2200000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000927013790000030128f3f500042f0cb3002f001f001f084b0417000500f3f500042f0cb3002f001f001f08660717000500000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000b690";
            };
            config = {
              eDP-1 = {
                enable = true;
                primary = false;
                mode = "1920x1200";
                rate = "59.88";
                position = "0x0";
              };
              DP-1 = { 
                enable = true;
                primary = true;
                mode = "2560x1440";
                rate = "144.0";
                position = "1920x0";
              };
            };
          };
          "dockedclamshell" = {
            fingerprint = {
              DP-1 = "00ffffffffffff0061a9012701000000141e0103803c2178afebc5ad4f45af270c5054a5cb0081c081809500a9c0b300d1c0a9c00101565e00a0a0a029503020350055502100001a000000ff0032373537353030303130313033000000fd0030901ef03c010a202020202020000000fc004d69204d6f6e69746f720a202001ec020346f34d0102030405901213141f4d5c3f23090707830100006a030c001000387820000067d85dc40178c0006d1a000002013090ed0000000000e3050301e6060000000000fd8180a070381f402040450055502100001ef5bd00a0a0a032502040450055502100001e9ee00078a0a032501040350055502100001e000000eb";
            };
            config = {
              DP-1 = {
                enable = true;
                primary = true;
                mode = "2560x1440";
                rate = "144.0";
              };
            };
          };
        };
      };
  };
  hardware = {
    opengl = {
      enable = true;
      extraPackages = with pkgs; [
        intel-media-driver
        vaapiVdpau
        libvdpau-va-gl
      ];
      driSupport = true;
      driSupport32Bit = true;
    };
  };
  system.stateVersion = "22.11"; # Did you read the comment?
}
