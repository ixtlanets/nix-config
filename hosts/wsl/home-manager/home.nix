{
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

  home = {
    username = "nik";
    homeDirectory = "/home/nik";
  };
  home.sessionVariables = {
    LD_LIBRARY_PATH = "/usr/lib/wsl/lib";
    NIXOS_OZONE_WL = "1";
  };

  home.sessionPath = [
    "/mnt/c/Users/nik/AppData/Local/Microsoft/WinGet/Packages/equalsraf.win32yank_Microsoft.Winget.Source_8wekyb3d8bbwe/"
    "/mnt/c/Users/nik/AppData/Local/Programs/Microsoft\ VS\ Code/bin"
  ];

  home.packages = with pkgs; [
    bzip2
    wslu
    vanilla-dmz
  ];

  catppuccin.flavor = "mocha";
  catppuccin.enable = true;
  catppuccin.nvim.enable = false;

  gtk.enable = true;
  gtk.iconTheme = {
    name = "Papirus-Dark";
    package = pkgs.catppuccin-papirus-folders.override {
      flavor = "mocha";
      accent = "maroon";
    };
  };
  qt.enable = true;
  qt.style.name = "kvantum";
  qt.platformTheme.name = "kvantum";
  home.pointerCursor = {
    name = "Bibata-Original-Ice";
    package = pkgs.bibata-cursors;
    gtk.enable = true;
    x11.enable = true;
    x11.defaultCursor = "Bibata-Original-Ice";
    size = 12; # Since I'm using 200% scaling on my monitor

  };
  # https://nixos.wiki/wiki/FAQ/When_do_I_update_stateVersion
  home.stateVersion = "24.11";
}
