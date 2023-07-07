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
        videoDrivers = [ "amdgpu" ];
        deviceSection = ''Option "TearFree" "true"'';
      };
      asusd.enable = true;
      autorandr = {
        enable = false;
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
              eDP = "00ffffffffffff004d105815000000002d1f0104a51d127807de50a3544c99260f505400000001010101010101010101010101010101ed7b80a070b047403020360020b410000018ed7b80a070b03e453020360020b410000018000000fd003078999920010a202020202020000000fc004c513133344e314a5735350a2000a0";
            };
            config = {
              eDP = {
                enable = true;
                primary = true;
                mode = "1920x1200";
                rate = "60.0";
              };
            };
          };
          "docked" = {
            fingerprint = {
              eDP = "00ffffffffffff004d105815000000002d1f0104a51d127807de50a3544c99260f505400000001010101010101010101010101010101ed7b80a070b047403020360020b410000018ed7b80a070b03e453020360020b410000018000000fd003078999920010a202020202020000000fc004c513133344e314a5735350a2000a0";
              HDMI-A-0 = "00ffffffffffff0061a9012701000000141e0103803c2178afebc5ad4f45af270c5054a5cb0081c081809500a9c0b300d1c0a9c00101565e00a0a0a029503020350055502100001a000000ff0032373537353030303130313033000000fd0030901ef03c010a202020202020000000fc004d69204d6f6e69746f720a202001ec020346f34d0102030405901213141f4d5c3f23090707830100006a030c001000387820000067d85dc40178c0006d1a000002013090ed0000000000e305e301e6060701605000fd8180a070381f402040450055502100001ef5bd00a0a0a032502040450055502100001e9ee00078a0a032501040350055502100001e00000053";
            };
            config = {
              eDP = {
                enable = true;
                primary = false;
                mode = "1920x1200";
                rate = "120.0";
                position = "0x0";
              };
              HDMI-A-0 = {
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
              HDMI-A-0 = "00ffffffffffff0061a9012701000000141e0103803c2178afebc5ad4f45af270c5054a5cb0081c081809500a9c0b300d1c0a9c00101565e00a0a0a029503020350055502100001a000000ff0032373537353030303130313033000000fd0030901ef03c010a202020202020000000fc004d69204d6f6e69746f720a202001ec020346f34d0102030405901213141f4d5c3f23090707830100006a030c001000387820000067d85dc40178c0006d1a000002013090ed0000000000e305e301e6060701605000fd8180a070381f402040450055502100001ef5bd00a0a0a032502040450055502100001e9ee00078a0a032501040350055502100001e00000053";
            };
            config = {
              HDMI-A-0 = {
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

  boot.blacklistedKernelModules = [ "nouveau" ];
  hardware = {
    opengl = {
      enable = true;
      extraPackages = with pkgs; [
        rocm-opencl-icd
        rocm-opencl-runtime
        amdvlk
      ];
      extraPackages32 = with pkgs; [
        driversi686Linux.amdvlk
      ];
      driSupport = true;
      driSupport32Bit = true;
    };
  };
  system.stateVersion = "22.11"; # Did you read the comment?
}
