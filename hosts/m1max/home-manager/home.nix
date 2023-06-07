{ inputs, outputs, lib, config, pkgs, ... }:
let
  mkTuple = lib.hm.gvariant.mkTuple;
in
{
  imports = [];

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

  home = {
    username = "nik";
    homeDirectory = lib.mkDefault "/Users/nik";
  };

  home.packages = with pkgs; [
    nixpkgs-fmt
    _1password
    _1password-gui
    git-credential-1password
  ];

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
    btop.enable = true;
    htop.enable = true;
  };
  home.file.".inputrc".source = ../../../dotfiles/inputrc;

  # https://nixos.wiki/wiki/FAQ/When_do_I_update_stateVersion
  home.stateVersion = "22.11";
}