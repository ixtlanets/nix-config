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
    ./syncthing.nix
  ];

  fonts.fontconfig.enable = true;

  home = {
    username = "nik";
    homeDirectory = "/home/nik";
  };
  home.sessionVariables = {
    LD_LIBRARY_PATH = "/usr/lib/wsl/lib";
    NIXOS_OZONE_WL = "1";
    BROWSER = "wslview";
    DISPLAY = ":0";
    WAYLAND_DISPLAY = "wayland-0";
  };

  # Windows paths needed from WSL. These are also re-added in initContent
  # after stripping the full auto-appended Windows PATH to reduce zsh lag.
  home.sessionPath = [
    "/mnt/c/Users/sniku/AppData/Local/Microsoft/WinGet/Packages/equalsraf.win32yank_Microsoft.Winget.Source_8wekyb3d8bbwe/"
    "/mnt/c/Users/sniku/AppData/Local/Programs/Microsoft VS Code/bin"
    "/mnt/c/Users/sniku/AppData/Local/Obsidian"
    "/mnt/c/Windows"
  ];

  programs.zsh.initContent = ''
    # WSL appends the entire Windows PATH (~30 entries) which causes noticeable
    # lag in zsh syntax highlighting. Strip all /mnt/ paths and re-add only
    # the Windows tools we actually need.
    export PATH=$(printf '%s' "$PATH" | tr ':' '\n' | grep -v '^/mnt/' | tr '\n' ':' | sed 's/:*$//')
    export PATH="$PATH:/mnt/c/Windows:/mnt/c/Users/sniku/AppData/Local/Obsidian:/mnt/c/Users/sniku/AppData/Local/Microsoft/WinGet/Packages/equalsraf.win32yank_Microsoft.Winget.Source_8wekyb3d8bbwe:/mnt/c/Users/sniku/AppData/Local/Programs/Microsoft VS Code/bin"
  '';

  home.packages = with pkgs; [
    bzip2
    wslu
    wsl-open
    wl-clipboard
    vanilla-dmz
  ];

  catppuccin.flavor = "mocha";
  catppuccin.enable = true;
  catppuccin.nvim.enable = false;

  gtk.enable = true;
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
