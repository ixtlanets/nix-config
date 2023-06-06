# This is your home-manager configuration file
# Use this to configure your home environment (it replaces ~/.config/nixpkgs/home.nix)

{ inputs, outputs, lib, config, pkgs, ... }:
let
  mkTuple = lib.hm.gvariant.mkTuple;
in
{
  # You can import other home-manager modules here
  imports = [
    # If you want to use modules your own flake exports (from modules/home-manager):
    # outputs.homeManagerModules.example

    # Or modules exported from other flakes (such as nix-colors):
    # inputs.nix-colors.homeManagerModules.default

    # You can also split up your configuration and import pieces of it here:
    # ./nvim.nix
  ];

  nixpkgs = {
    # You can add overlays here
    overlays = [
      # Add overlays your own flake exports (from overlays and pkgs dir):
      outputs.overlays.additions
      outputs.overlays.modifications
      outputs.overlays.unstable-packages

      # You can also add overlays exported from other flakes:
      # neovim-nightly-overlay.overlays.default

      # Or define it inline, for example:
      (final: prev: {
        tmuxPluginsDracula = final.tmuxPlugins.dracula.overrideAttrs (oldAttrs: {
          version = "2.2.0";
          src = pkgs.fetchFromGitHub {
            owner = "dracula";
            repo = "tmux";
            rev = "v2.2.0";
            sha256 = "9p+KO3/SrASHGtEk8ioW+BnC4cXndYx4FL0T70lKU2w=";
          };
        });
      })

    ];
    # Configure your nixpkgs instance
    config = {
      # Disable if you don't want unfree packages
      allowUnfree = true;
      # Workaround for https://github.com/nix-community/home-manager/issues/2942
      allowUnfreePredicate = (_: true);
    };
  };

  # TODO: Set your username
  home = {
    username = "nik";
    homeDirectory = "/home/nik";
  };

  # Add stuff for your user as you see fit:
  # programs.neovim.enable = true;
  home.packages = with pkgs; [
    nixpkgs-fmt
    _1password
    _1password-gui
    git-credential-1password
    telegram-desktop
    obsidian
    moonlight-qt
    xclip
    nerdfonts
    wl-clipboard
    variety
    prismlauncher

    gnomeExtensions.tray-icons-reloaded
    gnomeExtensions.dash-to-panel
    gnomeExtensions.just-perfection
    gnomeExtensions.caffeine
    gnomeExtensions.bluetooth-quick-connect
    gnomeExtensions.gsconnect # kdeconnect enabled in default.nix
  ];

  # Enable home-manager and git
  programs = {
    home-manager.enable = true;
    alacritty = {
      enable = true;
      settings = {
        font = {
          normal.family = "Hack Nerd Font";
          size = 16;
        };
      };
    };
    bat = {
      enable = true;
    };
    gh = {
      enable = true;
      enableGitCredentialHelper = true;
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
    git = {
      enable = true;
      diff-so-fancy.enable = true;
      lfs.enable = true;
      userEmail = "snikulin@gmail.com";
      userName = "Sergey Nikulin";
    };
    zsh = {
      enable = true;
      enableAutosuggestions = true;
      enableCompletion = true;
      enableSyntaxHighlighting = true;
      history = {
        expireDuplicatesFirst = true;
        ignoreDups = true;
      };
    };
    fzf = {
      enable = true;
    };
    neovim = {
      enable = true;
      viAlias = true;
      vimAlias = true;
      withNodeJs = true;
      plugins = with pkgs.vimPlugins; [
        vim-fugitive
        vim-rhubarb
        vim-sleuth
        nvim-lspconfig
        mason-nvim
        mason-lspconfig-nvim
        fidget-nvim
        neodev-nvim
        nvim-cmp
        cmp-nvim-lsp
        luasnip
        cmp_luasnip
        which-key-nvim
        gitsigns-nvim
        onedark-nvim
        lualine-nvim
        indent-blankline-nvim
        comment-nvim
        telescope-nvim
        plenary-nvim
        telescope-fzf-native-nvim
        nvim-treesitter
        nvim-treesitter-textobjects
        copilot-vim
      ];
      extraLuaConfig = ''
        vim.g.mapleader = ' '
        vim.g.maplocalleader = ' '
        vim.cmd.colorscheme 'onedark'
        --------
        -- Set highlight on search
        vim.o.hlsearch = false

        -- Make line numbers default
        vim.wo.number = true
        vim.opt.relativenumber = true

        -- Enable mouse mode
        vim.o.mouse = 'a'

        -- Sync clipboard between OS and Neovim.
        --  Remove this option if you want your OS clipboard to remain independent.
        --  See `:help 'clipboard'`
        vim.o.clipboard = 'unnamedplus'

        -- Enable break indent
        vim.o.breakindent = true

        -- Save undo history
        vim.o.undofile = true

        -- Case insensitive searching UNLESS /C or capital in search
        vim.o.ignorecase = true
        vim.o.smartcase = true

        -- Keep signcolumn on by default
        vim.wo.signcolumn = 'yes'

        -- Decrease update time
        vim.o.updatetime = 250
        vim.o.timeout = true
        vim.o.timeoutlen = 300

        -- Set completeopt to have a better completion experience
        vim.o.completeopt = 'menuone,noselect'

        -- NOTE: You should make sure your terminal supports this
        vim.o.termguicolors = true

      '';
    };
    tmux = {
      enable = true;
      clock24 = true;
      baseIndex = 1;
      keyMode = "vi";
      plugins = [
        pkgs.tmuxPlugins.sensible
        pkgs.tmuxPlugins.pain-control
        pkgs.tmuxPlugins.urlview
        pkgs.tmuxPlugins.prefix-highlight
        {
          plugin = pkgs.tmuxPluginsDracula;
          extraConfig = ''
            set -g @dracula-show-fahrenheit false
            set -g @dracula-plugins "battery cpu-usage ram-usage weather time"
            set -g @dracula-show-left-icon session
            set -g @dracula-day-month true
            set -g @dracula-military-time true
          '';
        }
      ];
      extraConfig = ''

    '';
    };
    browserpass = {
      enable = true;
      browsers = [
        "firefox"
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
        {
          id = "dcpihecpambacapedldabdbpakmachpb";
          updateUrl = "https://raw.githubusercontent.com/iamadamdev/bypass-paywalls-chrome/master/updates.xml";
        }
      ];
    };
    btop.enable = true;
    htop.enable = true;
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


  # Nicely reload system units when changing configs
  systemd.user.startServices = "sd-switch";

  services.syncthing.enable = true;
  services.syncthing.tray.enable = true;

  # https://nixos.wiki/wiki/FAQ/When_do_I_update_stateVersion
  home.stateVersion = "22.11";
}
