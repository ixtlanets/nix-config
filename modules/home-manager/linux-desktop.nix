{
  pkgs,
  ...
}:
{

  home.packages = with pkgs; [
    browserpass
    telegram-desktop
    moonlight-qt
    xclip
    nerd-fonts.ubuntu
    nerd-fonts.ubuntu-mono
    nerd-fonts.ubuntu-sans
    nerd-fonts.sauce-code-pro
    nerd-fonts.hack
    monaspace
    variety
    prismlauncher
    zathura
    brightnessctl
    pamixer
    wireplumber
    mpv
    liberation_ttf
    font-awesome
    zoom-us
    obsidian
    wl-clipboard
    vscode
    pkgs.unstable.libreoffice-qt6-fresh
    google-antigravity
    code-cursor-fhs
  ];

  catppuccin.flavor = "mocha";
  catppuccin.enable = true;
  catppuccin.nvim.enable = false;
  catppuccin.alacritty.enable = true;

  programs = {
    alacritty = {
      enable = true;
      settings = {
        env.TERM = "xterm-256color";
        font = {
          normal.family = "Hack Nerd Font";
          size = 14;
        };
      };
    };
    zed-editor = {
      enable = true;
    };
    browserpass = {
      enable = true;
      browsers = [
        "brave"
        "firefox"
        "chromium"
      ];
    };

    chromium = {
      enable = true;
      extensions = [
        { id = "ddkjiahejlhfcafbddmgiahcphecmpfh"; } # ublock origin lite, since Google broken proper extensions
        { id = "mnjggcdmjocbbbhaepdhchncahnbgone"; } # SponsorBlock for YouTube - Skip Sponsorships
        { id = "naepdomgkenhinolocfifgehidddafch"; } # Browserpass
        { id = "enamippconapkdmgfgjchkhakpfinmaj"; } # DeArrow. dearrow.ajay.app
        { id = "hipekcciheckooncpjeljhnekcoolahp"; } # Tabliss - A Beautiful New Tab
        { id = "edibdbjcniadpccecjdfdjjppcpchdlm"; } # I still don't care about cookies
        { id = "ponfpcnoihfmfllpaingbgckeeldkhle"; } # Enhancer for YouTube
      ];
    };
    brave = {
      enable = true;
      extensions = [
        { id = "cjpalhdlnbpafiamejdnhcphjbkeiagm"; } # ublock origin
        { id = "mnjggcdmjocbbbhaepdhchncahnbgone"; } # SponsorBlock for YouTube - Skip Sponsorships
        { id = "kcpnkledgcbobhkgimpbmejgockkplob"; } # Tracking Token Stripper
        { id = "gebbhagfogifgggkldgodflihgfeippi"; } # Return YouTube Dislike
        { id = "naepdomgkenhinolocfifgehidddafch"; } # Browserpass
        { id = "enamippconapkdmgfgjchkhakpfinmaj"; } # DeArrow. dearrow.ajay.app
        { id = "hipekcciheckooncpjeljhnekcoolahp"; } # Tabliss - A Beautiful New Tab
        { id = "edibdbjcniadpccecjdfdjjppcpchdlm"; } # I still don't care about cookies
        { id = "ponfpcnoihfmfllpaingbgckeeldkhle"; } # Enhancer for YouTube
        {
          id = "dcpihecpambacapedldabdbpakmachpb";
          updateUrl = "https://raw.githubusercontent.com/iamadamdev/bypass-paywalls-chrome/master/src/updates/updates.xml";
        }
      ];
      commandLineArgs = [ "--disable-features=WaylandWpColorManagerV1" ]; # fix for crash on hyprland
    };

    obs-studio = {
      enable = true;
      plugins = with pkgs.obs-studio-plugins; [
        wlrobs
        obs-backgroundremoval
        obs-pipewire-audio-capture
      ];
    };
  };

  xresources.extraConfig = builtins.readFile ../../dotfiles/Xresources;
  xdg.configFile."variety/variety.conf".text = builtins.readFile ../../dotfiles/variety.conf;
  xdg.configFile."variety/pluginconfig/quotes/quotes.txt".text =
    builtins.readFile ../../dotfiles/quotes.txt;
  home.file."scripts/set_wallpaper" = {
    text = builtins.readFile scripts/set_wallpaper;
    executable = true;
  };

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
    size = 24;
  };
}
