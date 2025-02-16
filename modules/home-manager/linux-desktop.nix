{
  inputs,
  outputs,
  lib,
  config,
  pkgs,
  dpi,
  ghostty,
  ...
}:
let
  DPI = builtins.toString dpi;
  rofi_width = (builtins.toString (dpi * 5));
  rofi_height = (builtins.toString (dpi * 3));
  polybar_height = (builtins.toString (dpi * 0.1666));
in
{

  home.packages = with pkgs; [
    _1password
    brave
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
    wl-clipboard
    variety
    prismlauncher
    zathura
    libreoffice-fresh
    brightnessctl
    pamixer
    wireplumber
    discord
    swaybg
    swayimg
    mpv
    liberation_ttf
    font-awesome
    zoom-us
    zed-editor # code editor writen in Rust
    microsoft-edge # funny enough it's actually good browser
    (obsidian.overrideAttrs (oldAttrs: {
      postInstall = ''
        wrapProgram $out/bin/obsidian --add-flags "--ozone-platform=wayland --enable-wayland-ime"
      '';
    }))

    (_1password-gui.overrideAttrs (oldAttrs: {
      postInstall = ''
        wrapProgram $out/share/1password/1password --add-flags "--ozone-platform=wayland --enable-wayland-ime"
      '';
    }))
    ghostty.packages.x86_64-linux.default
  ];

  catppuccin.flavor = "mocha";
  catppuccin.enable = true;

  programs = {
    alacritty = {
      enable = true;
      catppuccin.enable = true;
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
      profiles.nik = {
        name = "Sergey Nikulin";
        isDefault = true;
        containers = {
          personal = {
            color = "blue";
            icon = "fingerprint";
            id = 1;
          };
          gr = {
            color = "green";
            icon = "dollar";
            id = 2;
          };
          rwdt = {
            color = "red";
            icon = "fence";
            id = 3;
          };
          loktar = {
            color = "yellow";
            icon = "circle";
            id = 4;
          };
        };
        settings = {
          "app.normandy.api_url" = "";
          "app.normandy.enabled" = false;
          "app.shield.optoutstudies.enabled" = false;
          "app.update.auto" = false;
          "beacon.enabled" = false;
          "breakpad.reportURL" = "";
          "browser.aboutConfig.showWarning" = false;
          "browser.cache.offline.enable" = false;
          "browser.crashReports.unsubmittedCheck.autoSubmit" = false;
          "browser.crashReports.unsubmittedCheck.autoSubmit2" = false;
          "browser.crashReports.unsubmittedCheck.enabled" = false;
          "browser.disableResetPrompt" = true;
          "browser.urlbar.trimURLs" = false;
        };
        search = {
          default = "google";
          force = true;
          engines = {
            "google" = {
              urls = [
                {
                  template = "https://www.google.com/search";
                  params = [
                    {
                      name = "q";
                      value = "{searchTerms}";
                    }
                  ];
                }
              ];
              definedAliases = [ "@s" ];
            };
            "Nix Packages" = {
              urls = [
                {
                  template = "https://search.nixos.org/packages";
                  params = [
                    {
                      name = "type";
                      value = "packages";
                    }
                    {
                      name = "query";
                      value = "{searchTerms}";
                    }
                  ];
                }
              ];
              definedAliases = [ "@n" ];
            };
            "Wikipedia" = {
              urls = [
                {
                  template = "https://en.wikipedia.org/wiki/Special:Search";
                  params = [
                    {
                      name = "search";
                      value = "{searchTerms}";
                    }
                  ];
                }
              ];
              definedAliases = [ "@w" ];
            };
          };
        };
      };
    };
    chromium = {
      enable = true;
      commandLineArgs = [
        "--ozone-platform-hint=auto"
      ];
      extensions = [
        { id = "cjpalhdlnbpafiamejdnhcphjbkeiagm"; } # ublock origin
        { id = "aeblfdkhhhdcdjpifhhbdiojplfjncoa"; } # 1Password
        { id = "mnjggcdmjocbbbhaepdhchncahnbgone"; } # SponsorBlock for YouTube - Skip Sponsorships
        { id = "kcpnkledgcbobhkgimpbmejgockkplob"; } # Tracking Token Stripper
        { id = "gebbhagfogifgggkldgodflihgfeippi"; } # Return YouTube Dislike
        { id = "naepdomgkenhinolocfifgehidddafch"; } # Browserpass
        { id = "enamippconapkdmgfgjchkhakpfinmaj"; } # DeArrow. dearrow.ajay.app
        { id = "fcphghnknhkimeagdglkljinmpbagone"; } # YouTube AutoHD. preselect video resolution
        { id = "hipekcciheckooncpjeljhnekcoolahp"; } # Tabliss - A Beautiful New Tab
        {
          id = "dcpihecpambacapedldabdbpakmachpb";
          updateUrl = "https://raw.githubusercontent.com/iamadamdev/bypass-paywalls-chrome/master/src/updates/updates.xml";
        }
      ];
    };
  };

  xresources.extraConfig = builtins.readFile ../../dotfiles/Xresources;
  # read rofi config and replace DPI with dpi
  xdg.configFile."rofi/config.rasi".text =
    builtins.replaceStrings [ "DPI" "WIDTH" "HEIGHT" ] [ DPI rofi_width rofi_height ]
      (builtins.readFile ../../dotfiles/rofi);
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
    hyprcursor.enable = true;
    hyprcursor.size = 32;
    size = 32;

  };
}
