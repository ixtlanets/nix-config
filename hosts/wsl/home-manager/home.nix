{ inputs, outputs, lib, config, pkgs, niknvim, ... }: 
{
  imports = [
    ../../../modules/home-manager/starship.nix
    ../../../modules/home-manager/tmux.nix
    ../../../modules/home-manager/common.nix
    ../../../modules/home-manager/emacs.nix
  ];

  fonts.fontconfig.enable = true;

  home = {
    username = "nik";
    homeDirectory = "/home/nik";
  };
  home.sessionVariables = {
    LD_LIBRARY_PATH = "/usr/lib/wsl/lib";
  };

  # https://nixos.wiki/wiki/FAQ/When_do_I_update_stateVersion
  home.stateVersion = "22.11";
}
