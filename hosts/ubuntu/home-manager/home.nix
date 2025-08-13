{
  inputs,
  outputs,
  lib,
  config,
  pkgs,
  ...
}:
{
  imports = [
    ../../../modules/home-manager/starship.nix
    ../../../modules/home-manager/tmux.nix
    ../../../modules/home-manager/common.nix
    ../../../modules/home-manager/emacs.nix
    ../../../modules/home-manager/nvim.nix
  ];

  fonts.fontconfig.enable = true;

  programs = {
    emacs = {
      package = lib.mkForce pkgs.emacs29;
    };
  };

  home = {
    username = "nik";
    homeDirectory = "/home/nik";
  };

  home.packages = with pkgs; [
    bzip2
    nerd-fonts.ubuntu
    nerd-fonts.ubuntu-mono
    nerd-fonts.ubuntu-sans
    nerd-fonts.sauce-code-pro
    nerd-fonts.hack
    monaspace
    liberation_ttf
    font-awesome
  ];
  # https://nixos.wiki/wiki/FAQ/When_do_I_update_stateVersion
  home.stateVersion = "24.11";
}
