{
  pkgs,
  dpi,
  ...
}:
let
  DPI = builtins.toString dpi;
  rofi_width = (builtins.toString (dpi * 5));
  rofi_height = (builtins.toString (dpi * 3));
in
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
    (obsidian.overrideAttrs (oldAttrs: {
      postInstall = ''
        wrapProgram $out/bin/obsidian --add-flags "--ozone-platform=wayland --enable-wayland-ime"
      '';
    }))

    warp-terminal # another fancy terminal. with AI features
  ];

  catppuccin.flavor = "mocha";
  catppuccin.enable = true;
  catppuccin.nvim.enable = false;

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
    zed-editor = {
      enable = true;
      extensions = [
        "anya"
        "nix"
        "caddyfile"
        "csv"
        "dart"
        "dockerfile"
        "docker-compose"
        "env"
        "make"
        "nginx"
        "org"
        "prisma"
        "ruby"
        "scss"
      ];
      extraPackages = [ pkgs.nixd ];
      userSettings = {
        "features" = {
          "inline_completion_provider" = "zed";
        };
        "assistant" = {
          "default_model" = {
            "provider" = "zed.dev";
            "model" = "claude-3-5-sonnet-latest";
          };
          "version" = "2";
        };
        "relative_line_numbers" = true;
        "vim_mode" = true;
        "ui_font_size" = 16;
        "buffer_font_family" = "Hack Nerd Font Mono";
        "terminal" = {
          "font_family" = "Hack Nerd Font Mono";
        };
        "buffer_font_size" = 16;
      };
    };
    vscode = {
      enable = true;

      package = pkgs.vscode.fhsWithPackages (ps: with ps; [ zlib openssl.dev pkg-config ]);
      enableUpdateCheck = false;
      mutableExtensionsDir = false;
      extensions = with pkgs.vscode-extensions; [
        catppuccin.catppuccin-vsc
        dbaeumer.vscode-eslint
        bbenoist.nix
        jnoortheen.nix-ide
        vscodevim.vim
        github.copilot
        github.copilot-chat
        github.vscode-pull-request-github
        github.codespaces
        ms-python.python
        ms-azuretools.vscode-docker
        ms-vscode-remote.remote-ssh
        editorconfig.editorconfig
        donjayamanne.githistory
        eamodio.gitlens
        # Golang
        golang.go
        mkhl.direnv
      ];
      userSettings = {
        "workbench.colorTheme" = "One Dark Pro";
        "window.menuBarVisibility" = "toggle";
        # Git settings
        "git.enableSmartCommit" = true;
        "git.confirmSync" = false;
        "git.autofetch" = true;
        "git.ignoreLegacyWarning" = true;
        "editor.lineNumbers" = "relative";
        "editor.fontLigatures" = true;
        "vim.easymotion" = true;
        "vim.incsearch" = true;
        "vim.useSystemClipboard" = true;
        "vim.useCtrlKeys" = true;
        "vim.hlsearch" = true;
        "vim.insertModeKeyBindings" = [
          {
            before = ["j" "j"];
            after = ["<Esc>"];
          }
        ];
        "vim.normalModeKeyBindingsNonRecursive" = [
          {
            before = ["<leader>" "d"];
            after = ["d" "d"];
          }
          {
            before = ["<C-n>"];
            commands = [":nohl"];
          }
          {
            before = ["K"];
            commands = ["lineBreakInsert"];
            silent = true;
          }
        ];
        "vim.leader" = "<space>";
        "vim.handleKeys" = {
          "<C-a>" = false;
          "<C-f>" = false;
          "<C-b>" = false;
          "<C-p>" = false;
        };
        "extensions.experimental.affinity" = {
          "vscodevim.vim" = 1;
        };
        "editor.fontFamily" = "Hack Nerd Font";
        "editor.fontSize" = 16;
        "terminal.integrated.fontFamily" = "Hack Nerd Font";
        "terminal.integrated.fontSize" = 16;
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
        { id = "edibdbjcniadpccecjdfdjjppcpchdlm"; } # I still don't care about cookies
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
    hyprcursor.enable = true;
    hyprcursor.size = 24;
    size = 24;

  };
}
