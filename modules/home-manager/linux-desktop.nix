{ inputs, outputs, lib, config, pkgs, ... }: 
let
  mkTuple = lib.hm.gvariant.mkTuple;
in
{
  home.packages = with pkgs; [
    _1password
    _1password-gui
    brave
    browserpass
    git-credential-1password
    telegram-desktop
    obsidian
    moonlight-qt
    xclip
    nerdfonts
    wl-clipboard
    variety
    prismlauncher
    zathura
    onlyoffice-bin
    brightnessctl
    pamixer
    wireplumber
    discord
    swaybg
    mpv
    liberation_ttf
    font-awesome
    zoom-us
  ];

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
    vscode = {
      enable = true;
      package = pkgs.vscode.fhs;
      extensions = with pkgs.vscode-extensions; [
        catppuccin.catppuccin-vsc
        dbaeumer.vscode-eslint
        bbenoist.nix
        jnoortheen.nix-ide
        github.copilot
        github.vscode-pull-request-github
        github.codespaces
      ];
      userSettings = {
        "editor.fontFamily" = "'Hack Nerd Font', 'Droid Sans Mono', 'monospace', monospace";
        "editor.fontSize" = 16;
        "editor.lineNumbers" = "relative";
        "window.menuBarVisibility" = "toggle";
        "window.titleBarStyle" = "custom";
        "editor.inlineSuggest.enabled" = true;
      };
    };
    browserpass = {
      enable = true;
      browsers = [
        "brave"
        "firefox"
        "chromium"
      ];
    };
    firefox = {
      enable = true;
    };
    chromium = {
      enable = true;
      commandLineArgs = [
        "--ozone-platform-hint=auto"
        "--enable-gpu-rasterization"
        "--enable-zero-copy"
        "--ozone-platform-hint=wayland"
      ];
      extensions = [
        { id = "cjpalhdlnbpafiamejdnhcphjbkeiagm"; } # ublock origin
        { id = "aeblfdkhhhdcdjpifhhbdiojplfjncoa"; } # 1Password
        { id = "mbmgnelfcpoecdepckhlhegpcehmpmji"; } # SponsorBlock for YouTube - Skip Sponsorships
        { id = "kcpnkledgcbobhkgimpbmejgockkplob"; } # Tracking Token Stripper
        { id = "gebbhagfogifgggkldgodflihgfeippi"; } # Return YouTube Dislike
        { id = "naepdomgkenhinolocfifgehidddafch"; } # Browserpass
        { id = "enamippconapkdmgfgjchkhakpfinmaj"; } # DeArrow. dearrow.ajay.app
        { id = "fcphghnknhkimeagdglkljinmpbagone"; } # YouTube AutoHD. preselect video resolution
        {
          id = "dcpihecpambacapedldabdbpakmachpb";
          updateUrl = "https://raw.githubusercontent.com/iamadamdev/bypass-paywalls-chrome/master/src/updates/updates.xml";
        }
      ];
    };
  };

  xresources.extraConfig = builtins.readFile ../../dotfiles/Xresources;
  xdg.configFile."rofi/config.rasi".text = builtins.readFile ../../dotfiles/rofi;
  xdg.configFile."variety/variety.conf".text = builtins.readFile ../../dotfiles/variety.conf;
  xdg.configFile."variety/pluginconfig/quotes/quotes.txt".text = builtins.readFile ../../dotfiles/quotes.txt;
  home.file."scripts/set_wallpaper" = {
    text = builtins.readFile scripts/set_wallpaper;
    executable = true;
  };
  home.pointerCursor = {
    name = "Vanilla-DMZ";
    package = pkgs.vanilla-dmz;
    size = 32;
    gtk.enable = true;
    x11.enable = true;
  };
}
