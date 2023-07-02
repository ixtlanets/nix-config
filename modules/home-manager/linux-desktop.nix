{ inputs, outputs, lib, config, pkgs, ... }: 
let
  mkTuple = lib.hm.gvariant.mkTuple;
in
{
  home.packages = with pkgs; [
    _1password
    _1password-gui
    browserpass
    git-credential-1password
    telegram-desktop
    obsidian
    moonlight-qt
    xclip
    nerdfonts
    wl-clipboard
    variety
    feh
    prismlauncher
    rofi-wayland
    zathura
    onlyoffice-bin
    brightnessctl
    pamixer
    mako
    wireplumber
    discord
    swaybg
    maim # screenshot tool
    mpv
  ];

  programs = {
    alacritty = {
      enable = true;
      settings = {
        env.TERM = "xterm-256color";
        font = {
          normal.family = "Hack Nerd Font";
          size = 10;
        };
      };
    };
    vscode = {
      enable = true;
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
        {
          id = "dcpihecpambacapedldabdbpakmachpb";
          updateUrl = "https://raw.githubusercontent.com/iamadamdev/bypass-paywalls-chrome/master/updates.xml";
        }
      ];
    };
    i3status = {
      enable = true;

      general = {
        colors = true;
        color_good = "#8C9440";
        color_bad = "#A54242";
        color_degraded = "#DE935F";
      };

      modules = {
        ipv6.enable = false;
        "wireless _first_".enable = true;
        "battery all".enable = true;
        "volume master" = {
          position = 1;
          settings = {
            format = "♪ %volume";
            format_muted = "♪ muted (%volume)";
            device = "pulse:1";
          };
        };
      };
    };
  };

  xresources.extraConfig = builtins.readFile .dotfiles/Xresources;
  xdg.configFile."i3/config".text = builtins.readFile .dotfiles/i3;
  xdg.configFile."rofi/config.rasi".text = builtins.readFile .dotfiles/rofi;
  xdg.configFile."variety/variety.conf".text = builtins.readFile .dotfiles/variety.conf;
  xdg.configFile."variety/pluginconfig/quotes/quotes.txt".text = builtins.readFile .dotfiles/quotes.txt;
  home.file."scripts/set_wallpaper" = {
    text = builtins.readFile scripts/set_wallpaper;
    executable = true;
  };
  home.pointerCursor = {
    name = "Vanilla-DMZ";
    package = pkgs.vanilla-dmz;
    size = 48;
    x11.enable = true;
  };
  services.picom = {
    enable = true;
    shadow = true;
    backend = "glx";
    inactiveOpacity = 0.8;
    vSync = true;
  };
  services.network-manager-applet.enable = true;
  services.mako = {
    enable = true;
    borderRadius = 5;
    defaultTimeout = 3000;
    extraConfig = ''
      background-color=#24273a
      text-color=#cad3f5
      border-color=#8aadf4
      progress-color=over #363a4f

      [urgency=high]
      border-color=#f5a97f
        '';
  };
}
