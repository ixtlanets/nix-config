# This is your home-manager configuration file
# Use this to configure your home environment (it replaces ~/.config/nixpkgs/home.nix)

{
  pkgs,
  lib,
  dpi,
  ...
}:
{
  home.sessionVariables = lib.mkForce (
    let
      scale = dpi / 96.0;
      scaleStr = builtins.toString scale;
    in
    {
      WIFI_INTERFACE = "wlo1";
      HWMON_PATH = "/sys/devices/platform/coretemp.0/hwmon/hwmon5/temp1_input";
      THERMAL_ZONE = "10";
      BACKLIGHT_CARD = "intel_backlight";
      GDK_SCALE = "1";
      QT_AUTO_SCREEN_SCALE_FACTOR = "1";
      QT_SCALE_FACTOR_ROUNDING_POLICY = "PassThrough";
      STEAM_FORCE_DESKTOPUI_SCALING = scaleStr;
    }
  );
  # You can import other home-manager modules here
  imports = [
    ../../../modules/home-manager/starship.nix
    ../../../modules/home-manager/tmux.nix
    ../../../modules/home-manager/common.nix
    ../../../modules/home-manager/services.nix
    ../../../modules/home-manager/emacs.nix
    ../../../modules/home-manager/linux-desktop.nix
    ../../../modules/home-manager/gnome.nix
    ../../../modules/home-manager/kbd-backlight.nix
    ../../../modules/home-manager/email.nix
    ../../../modules/home-manager/nvim.nix
    ../../../modules/home-manager/ghostty.nix
  ];

  home = {
    username = "nik";
    homeDirectory = "/home/nik";
  };

  home.packages = with pkgs; [
    asusctl
    supergfxctl
    nvtopPackages.full

    gnomeExtensions.gpu-supergfxctl-switch
  ];
  xresources.properties = {
    "Xft.dpi" = dpi;
  };

  # https://nixos.wiki/wiki/FAQ/When_do_I_update_stateVersion
  home.stateVersion = "24.11";
}
