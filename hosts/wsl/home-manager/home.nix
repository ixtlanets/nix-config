{ inputs, outputs, lib, config, pkgs, niknvim, ... }: 
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
      package = lib.mkForce pkgs.emacs29-pgtk;
    };
  };

  home = {
    username = "nik";
    homeDirectory = "/home/nik";
  };
  home.sessionVariables = {
    LD_LIBRARY_PATH = "/usr/lib/wsl/lib";
    NIXOS_OZONE_WL = "1";
  };

  home.packages = with pkgs; [
    wslu
    vanilla-dmz
  ];
  # https://nixos.wiki/wiki/FAQ/When_do_I_update_stateVersion
  home.stateVersion = "22.11";
}
