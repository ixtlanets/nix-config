# This is your home-manager configuration file
# Use this to configure your home environment (it replaces ~/.config/nixpkgs/home.nix)

{
  pkgs,
  dpi,
  ...
}:
{
  home.sessionVariables = {
    WIFI_INTERFACE = "wlp6s0";
    HWMON_PATH = "/sys/devices/virtual/thermal/thermal_zone0/hwmon5/temp1_input";
    THERMAL_ZONE = "0";
    BACKLIGHT_CARD = "amdgpu_bl0";
    STEAM_FORCE_DESKTOPUI_SCALING = 2;
  };
  # You can import other home-manager modules here
  imports = [
    ../../../modules/home-manager/starship.nix
    ../../../modules/home-manager/tmux.nix
    ../../../modules/home-manager/common.nix
    ../../../modules/home-manager/services.nix
    ../../../modules/home-manager/emacs.nix
    ../../../modules/home-manager/linux-desktop.nix
    ../../../modules/home-manager/waybar.nix
     ../../../modules/home-manager/hyprland.nix
     ../../../modules/home-manager/kbd-backlight.nix
     ../../../modules/home-manager/email.nix
     ../../../modules/home-manager/nvim.nix
     ../../../modules/home-manager/ghostty.nix
     ../../../modules/home-manager/wezterm.nix
  ];

  dconf.settings = {
    "org/gnome/desktop/interface" = {
      text-scaling-factor = 1.0;
    };
  };
  home = {
    username = "nik";
    homeDirectory = "/home/nik";
  };

  home.packages = with pkgs; [
    asusctl
    supergfxctl
    nvtopPackages.full
  ];

  xresources.properties = {
    "Xft.dpi" = dpi;
  };

  # https://nixos.wiki/wiki/FAQ/When_do_I_update_stateVersion
  home.stateVersion = "24.11";
}
