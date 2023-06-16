{ inputs, outputs, lib, config, pkgs, ... }:
let
  mkTuple = lib.hm.gvariant.mkTuple;
in
{
  imports = [ 
    ../../../modules/home-manager/starship.nix
    ../../../modules/home-manager/tmux.nix
    ../../../modules/home-manager/common.nix
  ];

  nixpkgs = {
    # You can add overlays here
    overlays = [
      # Add overlays your own flake exports (from overlays and pkgs dir):
      outputs.overlays.additions
      outputs.overlays.modifications
      outputs.overlays.unstable-packages
    ];
    # Configure your nixpkgs instance
    config = {
      # Disable if you don't want unfree packages
      allowUnfree = true;
      # Workaround for https://github.com/nix-community/home-manager/issues/2942
      allowUnfreePredicate = (_: true);
    };
  };

  home = {
    username = "nik";
    homeDirectory = lib.mkDefault "/Users/nik";
  };

  home.packages = with pkgs; [
    nixpkgs-fmt
    _1password
    _1password-gui
    git-credential-1password
  ];

  programs = {
    home-manager.enable = true;
    alacritty = {
      enable = true;
      settings = {
        font = {
          normal.family = "Hack Nerd Font";
          size = 16;
        };
      };
    };
    bat = {
      enable = true;
    };
    gh = {
      enable = true;
      enableGitCredentialHelper = true;
    };
    git = {
      enable = true;
      diff-so-fancy.enable = true;
      lfs.enable = true;
      userEmail = "snikulin@gmail.com";
      userName = "Sergey Nikulin";
    };
    zsh = {
      enable = true;
      enableAutosuggestions = true;
      enableCompletion = true;
      enableSyntaxHighlighting = true;
      history = {
        expireDuplicatesFirst = true;
        ignoreDups = true;
      };
    };
    fzf = {
      enable = true;
    };
    btop.enable = true;
    htop.enable = true;
  };
  home.file.".inputrc".source = ../../../dotfiles/inputrc;

  # https://nixos.wiki/wiki/FAQ/When_do_I_update_stateVersion
  home.stateVersion = "22.11";
}
