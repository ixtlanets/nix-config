{ inputs, outputs, lib, config, pkgs, ... }:
{

  home.packages = with pkgs; [
    nerdfonts
    cantarell-fonts
    cmake
    libvterm
    libtool
  ];
  programs = {
    emacs = {
      enable = true;
      package = pkgs.emacs29-pgtk;
      extraPackages = epkgs: with epkgs; [
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
        hydra
      ];
    };
  };
}
