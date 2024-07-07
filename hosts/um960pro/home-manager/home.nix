
# This is your home-manager configuration file
# Use this to configure your home environment (it replaces ~/.config/nixpkgs/home.nix)

{ inputs, outputs, lib, config, pkgs, niknvim, dpi, ... }: 
{
  home.sessionVariables = {
  };
  # You can import other home-manager modules here
  imports = [
    ../../../modules/home-manager/starship.nix
    ../../../modules/home-manager/tmux.nix
    ../../../modules/home-manager/common.nix
    ../../../modules/home-manager/services.nix
    ../../../modules/home-manager/emacs.nix
    ../../../modules/home-manager/linux-desktop.nix
    ../../../modules/home-manager/gnome.nix
    ../../../modules/home-manager/hyprland.nix
    ../../../modules/home-manager/waybar.nix
    ../../../modules/home-manager/foot.nix
    ../../../modules/home-manager/email.nix
    ../../../modules/home-manager/nvim.nix
    ../../../modules/home-manager/ollama.nix
  ];
  wayland.windowManager.hyprland.settings = {
    monitor = [
        "HDMI-A-1,2560x1440@144Hz,auto,1.6"
        "DP-2,3840x2560@60Hz,auto,2"
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
  home.stateVersion = "22.11";
}

