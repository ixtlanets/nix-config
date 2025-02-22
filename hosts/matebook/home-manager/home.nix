# This is your home-manager configuration file
# Use this to configure your home environment (it replaces ~/.config/nixpkgs/home.nix)

{ inputs, outputs, lib, config, pkgs, niknvim, dpi, ... }: 
{
  # You can import other home-manager modules here
  imports = [
    ../../../modules/home-manager/starship.nix
    ../../../modules/home-manager/tmux.nix
    ../../../modules/home-manager/common.nix
    ../../../modules/home-manager/services.nix
    ../../../modules/home-manager/emacs.nix
    ../../../modules/home-manager/linux-desktop.nix
    ../../../modules/home-manager/sway.nix
    ../../../modules/home-manager/kanshi.nix
  ];
  wayland.windowManager.hyprland.settings = {
    monitor = [
      "eDP-1,3120x2080@90.000Hz,auto,3.0"
    ];
    bindl = [
    ", switch:on:Lid Switch, exec, hyprctl keyword monitor \"eDP-1, disable\""
    ", switch:off:Lid Switch, exec, hyprctl keyword monitor \"eDP-1, ,3120x2080@90.000Hz, 0x0, 3\""
    ];
  };

  home = {
    username = "nik";
    homeDirectory = "/home/nik";
  };
  
  home.packages = with pkgs; [
    nvtop
  ];
  xresources.properties = {
    "Xft.dpi" = dpi;
  };


  # https://nixos.wiki/wiki/FAQ/When_do_I_update_stateVersion
  home.stateVersion = "24.11";
}
