{ inputs, outputs, lib, config, pkgs, niknvim, ... }: 
{
  nixpkgs = {
    # You can add overlays here
    overlays = [
      # Add overlays your own flake exports (from overlays and pkgs dir):
      outputs.overlays.additions
      outputs.overlays.modifications
      outputs.overlays.unstable-packages
    ];
    # Configure your nixpkgs instance
    config = {
      # Disable if you don't want unfree packages
      allowUnfree = true;
      # Workaround for https://github.com/nix-community/home-manager/issues/2942
      allowUnfreePredicate = (_: true);
    };
  };
  
  home.sessionVariables = {
    TZ_LIST = "Europe/London,London;America/New_York,NY;America/Los_Angeles,GR-office";
  };

  home.packages = with pkgs; [
    ffmpeg
    glow # markdown reader for terminal
    portal # file transfer
    tz # A time zone helper
    imagemagick
    parallel
    niknvim.packages."${system}".default
    nixpkgs-fmt
    nodejs
    bun # better than nodejs and npm
    gam # Google workspace admin cli
    (pkgs.python3.withPackages (p: with p; [
      ipython
      jupyter
    ]))
    imgp # fast image resizer
    ffmpegthumbnailer
    mediainfo
    nsxiv
    xdragon
    gnupg
    tabbed
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
      gitCredentialHelper.enable = true;
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
      syntaxHighlighting.enable = true;
      history = {
        expireDuplicatesFirst = true;
        ignoreDups = true;
      };
    };
    fzf = {
      enable = true;
    };
    password-store = {
      enable = true;
      package = pkgs.pass.withExtensions (exts: [ 
        exts.pass-otp 
        exts.pass-audit
        exts.pass-import
        exts.pass-genphrase
      ]);
      settings = {
        PASSWORD_STORE_DIR = "$HOME/.password-store";
      };
    };
    yt-dlp = {
      enable = true;
      settings = {
        "output" = "~/Video/YouTube/%(title)s.%(ext)s";
        "format" = "mp4";
      };
    };
    nnn = {
      enable = true;
      bookmarks = {
        d = "~/Documents";
        p = "~/pro";
      };
      extraPackages = with pkgs; [ ffmpegthumbnailer mediainfo nsxiv xdragon gnupg ];
      plugins = {
        mappings = {
          d = "dragdrop";
          e = "gpge";
          r = "imgresize";
          v = "imgview";
          p = "preview-tabbed";
        };
        src = (pkgs.fetchFromGitHub {
            owner = "jarun";
            repo = "nnn";
            rev = "v4.8";
            sha256 = "sha256-Hpc8YaJeAzJoEi7aJ6DntH2VLkoR6ToP6tPYn3llR7k=";
            }) + "/plugins";
      };
    };
  };
}
