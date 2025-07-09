{
  inputs,
  outputs,
  lib,
  config,
  pkgs,
  ...
}:
let
  mkTuple = lib.hm.gvariant.mkTuple;
in
{
  imports = [
    ../../../modules/home-manager/starship.nix
    ../../../modules/home-manager/tmux.nix
    ../../../modules/home-manager/common.nix
    ../../../modules/home-manager/services.nix
    ../../../modules/home-manager/email.nix
    ../../../modules/home-manager/nvim.nix
  ];

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

  targets.darwin.defaults = {
    NSGlobalDomain.AppleLanguages = [
      "en-RU"
      "ru-RU"
    ];
    NSGlobalDomain.AppleLocale = "en_RU";
    NSGlobalDomain.AppleMeasurementUnits = "Centimeters";
    NSGlobalDomain.AppleMetricUnits = true;
    NSGlobalDomain.AppleTemperatureUnit = "Celsius";
    NSGlobalDomain.NSAutomaticCapitalizationEnabled = true;
    NSGlobalDomain.NSAutomaticDashSubstitutionEnabled = false;
    NSGlobalDomain.NSAutomaticPeriodSubstitutionEnabled = false;
    NSGlobalDomain.NSAutomaticQuoteSubstitutionEnabled = false;
    NSGlobalDomain.NSAutomaticSpellingCorrectionEnabled = false;
    "com.apple.Safari".IncludeDevelopMenu = true;
    "com.apple.Safari".ShowOverlayStatusBar = true;
    "com.apple.desktopservices".DSDontWriteNetworkStores = true;
    "com.apple.desktopservices".DSDontWriteUSBStores = true;
  };
  targets.darwin.search = "Google";

  home = {
    username = "nik";
    homeDirectory = lib.mkDefault "/Users/nik";
  };

  home.packages = with pkgs; [
    nixpkgs-fmt
    ripgrep
    sqlite
    wordnet
  ];

  programs = {
    home-manager.enable = true;
    alacritty = {
      enable = true;
      settings = {
        env.TERM = "xterm-256color";
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
      gitCredentialHelper.enable = true;
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
      autosuggestion.enable = true;
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
    btop.enable = true;
    htop.enable = true;
  };
  home.file.".inputrc".source = ../../../dotfiles/inputrc;
  home.file.".config/ghostty/config".text = ''
    font-family = "Hack Nerd Font"
    font-size = 16
    theme = catppuccin-mocha
    quit-after-last-window-closed = true
    macos-non-native-fullscreen = true
    macos-option-as-alt = true
  '';
  programs = {
    brave = {
      enable = true;
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
      ];
    };
  };
  #home.file.".config/linearmouse/linearmouse.json" .source = ../../../dotfiles/linearmouse.json;

  # https://nixos.wiki/wiki/FAQ/When_do_I_update_stateVersion
  home.stateVersion = "24.11";
}
