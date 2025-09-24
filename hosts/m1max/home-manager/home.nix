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
  braveExtensionIds = [
    "cjpalhdlnbpafiamejdnhcphjbkeiagm" # ublock origin
    "aeblfdkhhhdcdjpifhhbdiojplfjncoa" # 1Password
    "mnjggcdmjocbbbhaepdhchncahnbgone" # SponsorBlock for YouTube - Skip Sponsorships
    "kcpnkledgcbobhkgimpbmejgockkplob" # Tracking Token Stripper
    "gebbhagfogifgggkldgodflihgfeippi" # Return YouTube Dislike
    "naepdomgkenhinolocfifgehidddafch" # Browserpass
    "enamippconapkdmgfgjchkhakpfinmaj" # DeArrow. dearrow.ajay.app
    "fcphghnknhkimeagdglkljinmpbagone" # YouTube AutoHD. preselect video resolution
    "hipekcciheckooncpjeljhnekcoolahp" # Tabliss - A Beautiful New Tab
    "edibdbjcniadpccecjdfdjjppcpchdlm" # I still don't care about cookies
  ];
  braveManagedPolicy =
    builtins.toJSON {
      ExtensionSettings = lib.listToAttrs (
        map (id: {
          name = id;
          value = {
            installation_mode = "force_installed";
            update_url = "https://clients2.google.com/service/update2/crx";
          };
        }) braveExtensionIds
      );
    };
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

  catppuccin.flavor = "mocha";
  catppuccin.enable = true;
  catppuccin.nvim.enable = false;
  catppuccin.alacritty.enable = true;

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
  home.file.".config/ghostty/themes/catppuccin-mocha".text = ''
    palette = 0=#45475a
    palette = 1=#f38ba8
    palette = 2=#a6e3a1
    palette = 3=#f9e2af
    palette = 4=#89b4fa
    palette = 5=#f5c2e7
    palette = 6=#94e2d5
    palette = 7=#a6adc8
    palette = 8=#585b70
    palette = 9=#f38ba8
    palette = 10=#a6e3a1
    palette = 11=#f9e2af
    palette = 12=#89b4fa
    palette = 13=#f5c2e7
    palette = 14=#94e2d5
    palette = 15=#bac2de
    background = 1e1e2e
    foreground = cdd6f4
    cursor-color = f5e0dc
    cursor-text = 11111b
    selection-background = 353749
    selection-foreground = cdd6f4
  '';
  home.file."Library/Application Support/BraveSoftware/Brave-Browser/Managed Policies/managed_policies.json".text = braveManagedPolicy;
  #home.file.".config/linearmouse/linearmouse.json" .source = ../../../dotfiles/linearmouse.json;

  home.sessionVariables = {
    OLLAMA_SERVICE_URL = "http://localhost:11434";
  };

  # https://nixos.wiki/wiki/FAQ/When_do_I_update_stateVersion
  home.stateVersion = "24.11";
}
