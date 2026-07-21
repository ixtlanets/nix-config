{
  config,
  lib,
  pkgs,
  ...
}:
let
  cfg = config.linuxDesktop;
  lmstudio = pkgs.unstable.lmstudio;
in
{
  imports = [ ./handy.nix ];

  options.linuxDesktop.enableMoonlight = lib.mkOption {
    type = lib.types.bool;
    default = true;
    description = "Whether to install Moonlight on Linux desktop hosts.";
  };

  config = {
    voiceTyping.handy.enable = lib.mkDefault true;
    voiceTyping.voxtype.enable = lib.mkDefault false;

    home.packages =
      with pkgs;
      [
        google-chrome
        telegram-desktop
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
        opencode-desktop
        vscode
        pkgs.unstable.libreoffice-qt6-fresh
        lmstudio
        google-antigravity
        code-cursor-fhs
        papirus-icon-theme
        kora-icon-theme
        vulkan-tools
      ]
      ++ lib.optionals cfg.enableMoonlight [
        moonlight-qt
      ];

    catppuccin.flavor = "mocha";
    catppuccin.enable = true;
    catppuccin.gtk.icon.enable = false;
    catppuccin.nvim.enable = false;
    catppuccin.alacritty.enable = true;

    programs = {
      alacritty = {
        enable = true;
        settings = {
          env.TERM = "xterm-256color";
          font = {
            normal.family = "Hack Nerd Font Mono";
            size = 14;
          };
        };
      };
      zed-editor = {
        enable = true;
      };
      firefox = {
        enable = true;
        configPath = ".mozilla/firefox";
        policies.ExtensionSettings = {
          "uBlock0@raymondhill.net" = {
            installation_mode = "force_installed";
            install_url = "https://addons.mozilla.org/firefox/downloads/latest/ublock-origin/latest.xpi";
          };
          "446900e4-71c2-419f-a6a7-df9c091e268b" = {
            installation_mode = "force_installed";
            install_url = "https://addons.mozilla.org/firefox/downloads/latest/bitwarden-password-manager/latest.xpi";
          };
          "sponsorBlocker@ajay.app" = {
            installation_mode = "force_installed";
            install_url = "https://addons.mozilla.org/firefox/downloads/latest/sponsorblock/latest.xpi";
          };
          "{9fda17be-849d-4f5b-a326-28d25f0f6d29}" = {
            installation_mode = "force_installed";
            install_url = "https://addons.mozilla.org/firefox/downloads/latest/utm-tracking-token-stripper/latest.xpi";
          };
          "deArrow@ajay.app" = {
            installation_mode = "force_installed";
            install_url = "https://addons.mozilla.org/firefox/downloads/latest/dearrow/latest.xpi";
          };
          "{2662ff67-b302-4363-95f3-b050218bd72c}" = {
            installation_mode = "force_installed";
            install_url = "https://addons.mozilla.org/firefox/downloads/latest/untrap-for-youtube/latest.xpi";
          };
          "extension@tabliss.io" = {
            installation_mode = "force_installed";
            install_url = "https://addons.mozilla.org/firefox/downloads/latest/tabliss/latest.xpi";
          };
          "jid1-KKzOGWgsW3Ao4Q@jetpack" = {
            installation_mode = "force_installed";
            install_url = "https://addons.mozilla.org/firefox/downloads/latest/i-dont-care-about-cookies/latest.xpi";
          };
          "enhancerforyoutube@maximerf.addons.mozilla.org" = {
            installation_mode = "force_installed";
            install_url = "https://addons.mozilla.org/firefox/downloads/latest/enhancer-for-youtube/latest.xpi";
          };
        };
      };

      chromium = {
        enable = true;
        extensions = [
          { id = "ddkjiahejlhfcafbddmgiahcphecmpfh"; } # ublock origin lite, since Google broken proper extensions
          { id = "nngceckbapebfimnlniiiahkandclblb"; } # Bitwarden
          { id = "mnjggcdmjocbbbhaepdhchncahnbgone"; } # SponsorBlock for YouTube - Skip Sponsorships
          { id = "enamippconapkdmgfgjchkhakpfinmaj"; } # DeArrow. dearrow.ajay.app
          { id = "enboaomnljigfhfjfoalacienlhjlfil"; } # Untrap - Remove YouTube Suggestions
          { id = "hipekcciheckooncpjeljhnekcoolahp"; } # Tabliss - A Beautiful New Tab
          { id = "edibdbjcniadpccecjdfdjjppcpchdlm"; } # I still don't care about cookies
          { id = "ponfpcnoihfmfllpaingbgckeeldkhle"; } # Enhancer for YouTube
        ];
      };
      brave = {
        enable = true;
        extensions = [
          { id = "cjpalhdlnbpafiamejdnhcphjbkeiagm"; } # ublock origin
          { id = "nngceckbapebfimnlniiiahkandclblb"; } # Bitwarden
          { id = "mnjggcdmjocbbbhaepdhchncahnbgone"; } # SponsorBlock for YouTube - Skip Sponsorships
          { id = "kcpnkledgcbobhkgimpbmejgockkplob"; } # Tracking Token Stripper
          { id = "enamippconapkdmgfgjchkhakpfinmaj"; } # DeArrow. dearrow.ajay.app
          { id = "enboaomnljigfhfjfoalacienlhjlfil"; } # Untrap - Remove YouTube Suggestions
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
      google-chrome = {
        enable = true;
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

    gtk = {
      enable = true;
      colorScheme = "dark";
      theme = {
        name = "catppuccin-mocha-blue-standard";
        package = pkgs.catppuccin-gtk.override {
          accents = [ "blue" ];
          size = "standard";
          variant = "mocha";
        };
      };
      iconTheme = {
        name = "kora";
        package = pkgs.kora-icon-theme;
      };
      gtk4.theme = {
        name = "catppuccin-mocha-blue-standard";
        package = pkgs.catppuccin-gtk.override {
          accents = [ "blue" ];
          size = "standard";
          variant = "mocha";
        };
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
      size = 24;
    };
  };
}
