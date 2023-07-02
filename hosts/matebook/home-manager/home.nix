# This is your home-manager configuration file
# Use this to configure your home environment (it replaces ~/.config/nixpkgs/home.nix)

{ inputs, outputs, lib, config, pkgs, niknvim, ... }: 
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
  ];
  wayland.windowManager.sway = {
    config = {
      output = {
        "eDP-1" = {
          mode = "3120x2080@90.000Hz";
          scale = "3";
        };
        "DP-1" = {
          mode = "2560x1440@144.000Hz";
          scale = "1.5";
        };
      };
    };
  };
  programs.waybar.settings.mainbar.output = [
    "eDP-1"
    "DP-1"
  ];

  home = {
    username = "nik";
    homeDirectory = "/home/nik";
  };
  
  home.packages = with pkgs; [
    nvtop
  ];
  xresources.properties = {
    "Xft.dpi" = 192;
  };


  # https://nixos.wiki/wiki/FAQ/When_do_I_update_stateVersion
  home.stateVersion = "22.11";
}
