{ inputs, outputs, lib, config, pkgs, niknvim, ... }: 
{
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
    homeDirectory = "/home/nik";
  };


  home.packages = with pkgs; [
    niknvim.packages."x86_64-linux".default
    nixpkgs-fmt
    nodejs
    (pkgs.python3.withPackages (p: with p; [
      ipython
      jupyter
    ]))
  ];

  # Enable home-manager and git
  programs = {
    home-manager.enable = true;
    bat = {
      enable = true;
    };
    btop.enable = true;
    htop.enable = true;
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
      extraConfig = {
        init.defaultBranch = "master";
      };
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
    password-store = {
      enable = true;
      package = pkgs.pass.withExtensions (exts: [ 
        exts.pass-otp 
        exts.pass-audit
        exts.pass-import
        exts.pass-genphrase
      ]);
    };
  };

  # Nicely reload system units when changing configs
  systemd.user.startServices = "sd-switch";

  services.syncthing.enable = true;
}
