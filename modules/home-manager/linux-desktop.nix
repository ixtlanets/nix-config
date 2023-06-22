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
    hyprland
    mako
    wireplumber
    xdg-desktop-portal-hyprland
    libsForQt5.polkit-kde-agent
    discord
    swaybg

    gnomeExtensions.tray-icons-reloaded
    gnomeExtensions.dash-to-panel
    gnomeExtensions.just-perfection
    gnomeExtensions.caffeine
    gnomeExtensions.bluetooth-quick-connect
    gnomeExtensions.gsconnect # kdeconnect enabled in default.nix
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
      };
    };
    waybar = {
      enable = true;
      settings = {
        mainBar = {
          layer = "top";
          position = "top";
          height = 30;
          output = [
            "eDP-1"
          ];
          modules-left = [ "wlr/workspaces" ];
          modules-center = [ "hyprland/window" ];
          modules-right = [ "temperature" "battery" "tray" "pulseaudio" ];
          "pulseaudio" = {
            format = "{volume}% {icon}";
            format-muted = "";
            scroll-step = 1;
          };
          "wlr/workspaces" = {
            format = "{name}";
          };
        };

      };
    };
  };

  dconf.settings = {
    "org/gnome/desktop/input-sources" = {
      sources = [ (mkTuple [ "xkb" "us" ]) (mkTuple [ "xkb" "ru" ]) ];
      xkb-options = [ "grp:win_space_toggle" "grp:win_space_toggle" ];
    };
    "org/gnome/desktop/wm/keybindings" = {
      close = [ "<Super>q" "<Alt>F4" ];
      maximize = [ "<Super>Up" ];
      unmaximize = [ "<Super>Down" ];
      toggle-fullscreen = [ "<Super>f" ];
      switch-to-workspace-left = [ "<Ctrl><Alt>Left" ];
      switch-to-workspace-right = [ "<Ctrl><Alt>Right" ];
      switch-to-workspace-1 = [ "<Ctrl><Alt>1" ];
      switch-to-workspace-2 = [ "<Ctrl><Alt>2" ];
      switch-to-workspace-3 = [ "<Ctrl><Alt>3" ];
      switch-to-workspace-4 = [ "<Ctrl><Alt>4" ];
      switch-to-workspace-5 = [ "<Ctrl><Alt>5" ];
      move-to-workspace-left = [ "<Shift><Ctrl><Alt>Left" ];
      move-to-workspace-right = [ "<Shift><Ctrl><Alt>Right" ];
      move-to-workspace-1 = [ "<Shift><Ctrl><Alt>1" ];
      move-to-workspace-2 = [ "<Shift><Ctrl><Alt>2" ];
      move-to-workspace-3 = [ "<Shift><Ctrl><Alt>3" ];
      move-to-workspace-4 = [ "<Shift><Ctrl><Alt>4" ];
      move-to-workspace-5 = [ "<Shift><Ctrl><Alt>5" ];
    };
    "org/gnome/settings-daemon/plugins/media-keys" = {
      custom-keybindings = [
        "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom0/"
        "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom1/"
        "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom2/"
      ];
    };
    "org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom0" = {
      binding = "<Super>Return";
      command = "alacritty";
      name = "open-terminal";
    };
    "org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom1" = {
      binding = "<Super>b";
      command = "chromium";
      name = "open-browser";
    };
    "org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom2" = {
      binding = "<Super>e";
      command = "nautilus";
      name = "open-file-browser";
    };
    "org/gnome/shell" = {
      favorite-apps = [
        "chromium-browser.desktop"
        "firefox.desktop"
        "Alacritty.desktop"
        "org.gnome.Nautilus.desktop"
        "org.telegram.desktop.desktop"
        "code.desktop"
      ];
      disable-user-extensions = false;
      enabled-extensions = [
        "trayIconsReloaded@selfmade.pl"
        "dash-to-panel@jderose9.github.com"
        "just-perfection-desktop@just-perfection"
        "caffeine@patapon.info"
        "bluetooth-quick-connect@bjarosze.gmail.com"
        "gsconnect@andyholmes.github.io"
      ];
    };
  };

  xresources.extraConfig = builtins.readFile .dotfiles/Xresources;
  xdg.configFile."i3/config".text = builtins.readFile .dotfiles/i3;
  xdg.configFile."rofi/config.rasi".text = builtins.readFile .dotfiles/rofi;
  xdg.configFile."variety/variety.conf".text = builtins.readFile .dotfiles/variety.conf;
  xdg.configFile."variety/pluginconfig/quotes/quotes.txt".text = builtins.readFile .dotfiles/quotes.txt;
  xdg.configFile."hypr/hyprland.conf".text = builtins.readFile .dotfiles/hyprland.conf;
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
    backend = "xr_glx_hybrid";
    inactiveOpacity = 0.8;
    vSync = true;
  };
  services.polybar = {
    enable = true;
    package = pkgs.polybarFull;
    script = "polybar mainbar-i3 &";
    config = .dotfiles/polybar.ini;
  };
  services.network-manager-applet.enable = true;
  services.dunst = {
    enable = true;
    settings = {
      global = {
        width = 300;
        height = 300;
        offset = "10x10";
        origin = "top-right";
        transparency = 10;
        frame_color = "#8AADF4";
        separator_color = "frame";
        font = "Hack Nerd Font 10";
      };
      urgency_low = {
        background = "#24273A";
        foreground = "#CAD3F5";
        timeout = 1;
      };

      urgency_normal = {
        background = "#24273A";
        foreground = "#CAD3F5";
        timeout = 3;
      };

      urgency_critical = {
        background = "#24273A";
        foreground = "#CAD3F5";
        frame_color = "#F5A97F";
        timeout = 3;
      };
    };
  };
}
