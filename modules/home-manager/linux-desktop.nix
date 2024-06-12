{ inputs, outputs, lib, config, pkgs, dpi, nur, ... }:
let
  DPI = builtins.toString dpi;
  rofi_width = (builtins.toString (dpi * 5));
  rofi_height = (builtins.toString (dpi * 3));
  polybar_height = (builtins.toString (dpi * 0.1666));

  token =
    lib.strings.removeSuffix "\n" (builtins.readFile ../../factorio.token);
  factorio = pkgs.factorio.override {
    username = "Ixtlanets";
    token = token;
  };
  factorio_token = builtins.readFile ../../factorio.token;

in
{


  home.packages = with pkgs; [
    _1password
    _1password-gui
    brave
    browserpass
    telegram-desktop
    obsidian
    moonlight-qt
    xclip
    nerdfonts
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

    factorio
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
        extensions = with config.nur.repos.rycee.firefox-addons; [
          onepassword-password-manager
            ublock-origin
            sponsorblock
            tabliss
            clearurls
            dearrow
#bypass-paywalls-clean
            istilldontcareaboutcookies
            multi-account-containers
        ];
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
          default = "searxng";
          force = true;
          engines = {
            "searxng" = {
              urls = [{
                template = "https://searxng.online/search";
                params = [
                { name = "q"; value = "{searchTerms}"; }
                ];
              }];
              definedAliases = [ "@s" ];
            };
            "Nix Packages" = {
              urls = [{
                template = "https://search.nixos.org/packages";
                params = [
                { name = "type"; value = "packages"; }
                { name = "query"; value = "{searchTerms}"; }
                ];
              }];
              definedAliases = [ "@n" ];
            };
            "Wikipedia" = {
              urls = [{
                template = "https://en.wikipedia.org/wiki/Special:Search";
                params = [
                { name = "search"; value = "{searchTerms}"; }
                ];
              }];
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
      { id = "mbmgnelfcpoecdepckhlhegpcehmpmji"; } # SponsorBlock for YouTube - Skip Sponsorships
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
  xdg.configFile."rofi/config.rasi".text = builtins.replaceStrings [ "DPI" "WIDTH" "HEIGHT" ] [ DPI rofi_width rofi_height ] (builtins.readFile ../../dotfiles/rofi);
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
