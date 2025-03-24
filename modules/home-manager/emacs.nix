{
  inputs,
  outputs,
  lib,
  config,
  pkgs,
  ...
}:
let
  isLinux = pkgs.stdenv.isLinux;
in
{

  home.packages =
    with pkgs;
    [
      nerd-fonts.ubuntu
      nerd-fonts.ubuntu-mono
      nerd-fonts.ubuntu-sans
      nerd-fonts.sauce-code-pro
      nerd-fonts.hack
      cantarell-fonts
      cmake
      libtool
      texliveFull
      nil
      graphviz
      ripgrep
      sqlite
      wordnet
    ]
    ++ (lib.optionals isLinux [
      libvterm
    ]);
  programs = {
    emacs = {
      enable = true;
      package = pkgs.emacs;
      extraPackages =
        epkgs: with epkgs; [
          use-package
          general
          org
          org-bullets
          visual-fill-column
          mu4e
          magit
          evil
          evil-collection
          evil-escape
          evil-surround
          evil-visualstar
          evil-nerd-commenter
          evil-matchit
          evil-args
          evil-exchange
          evil-indent-plus
          doom-themes
          doom-modeline
          all-the-icons
          which-key
          ivy
          ivy-rich
          ivy-prescient
          counsel
          helpful
          pdf-tools
          hydra
          vterm
          vertico
          marginalia
          nix-mode
        ];
    };
  };
}
