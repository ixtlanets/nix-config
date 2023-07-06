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

  home.packages = with pkgs; [
    ffmpeg
    niknvim.packages."${system}".default
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
    };
    yt-dlp = {
      enable = true;
      settings = {
        "output" = "~/Video/YouTube/%(title)s.%(ext)s";
        "format" = "mp4";
      };
    };
  };
}
