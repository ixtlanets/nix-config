{
  config,
  pkgs,
  inputs,
  ...
}:

let
  floxPkg = inputs.flox.packages.${pkgs.system}.default;
in
{
  nix.settings.experimental-features = [
    "nix-command"
    "flakes"
  ];

  nix.settings.substituters = [
    "https://cache.nixos.org"
    "https://devenv.cachix.org"
    "https://cache.flox.dev"
  ];
  nix.settings.trusted-substituters = [ "https://cache.flox.dev" ];
  nix.settings.trusted-public-keys = [
    "cache.nixos.org-1:6NCHdD59X431o0gWypbMrAURkbJ16ZPMQFGspcDShjY="
    "devenv.cachix.org-1:w1cLUi8dv3hnoSPGAuibQv+f9TZtWKshxzYfXc0fJyQ="
    "flox-cache-public-1:7F4OyH7ZCnFhcze3fJdfyXYLQw/aV7GEed86nQ7IsOs="
  ];

  networking.hostName = "m1max"; # Define your hostname.

  # Set your time zone.
  time.timeZone = "Europe/Moscow";

  programs.zsh.enable = true;

  users.users.nik = {
    home = "/Users/nik";
  };

  environment = {
    shells = with pkgs; [
      bash
      zsh
    ];
    systemPackages = [
      floxPkg
      pkgs.coreutils
    ];
    systemPath = [ "/opt/homebrew/bin" ];
    pathsToLink = [ "/Applications" ];
  };

  # Keyboard setttings
  system.keyboard.enableKeyMapping = true;
  system.keyboard.remapCapsLockToEscape = true;

  # Fonts
  fonts.packages = with pkgs; [
    nerd-fonts.ubuntu
    nerd-fonts.ubuntu-mono
    nerd-fonts.ubuntu-sans
    nerd-fonts.sauce-code-pro
    nerd-fonts.hack
  ];
  system.primaryUser = "nik";
  # mac defaults
  system.defaults = {
    finder.AppleShowAllExtensions = true;
    finder._FXShowPosixPathInTitle = true;
    finder.CreateDesktop = false;
    finder.FXEnableExtensionChangeWarning = false;
    finder.NewWindowTarget = "Home";
    finder.ShowPathbar = true; # show path bar
    finder.ShowStatusBar = true; # show status bar
    finder._FXSortFoldersFirst = true; # show folders before files in finder
    dock.autohide = false; # show dock
    dock.autohide-time-modifier = 0.0; # no stupid animation
    dock.mru-spaces = false; # Do not rearrange spaces
    dock.orientation = "right";
    dock.show-recents = false;
    dock.tilesize = 24; # smaller icons
    dock.expose-animation-duration = null; # no stupid animation
    dock.wvous-bl-corner = 1; # Disable Hot corner action for bottom left corner
    dock.wvous-br-corner = 1; # Disable Hot corner action for bottom right corner
    dock.wvous-tl-corner = 1; # Disable Hot corner action for top left corner
    dock.wvous-tr-corner = 1; # Disable Hot corner action for top right corner
    hitoolbox.AppleFnUsageType = "Do Nothing"; # Do nothing on "fn" key press
    NSGlobalDomain.AppleShowAllExtensions = true;
    NSGlobalDomain.InitialKeyRepeat = 14;
    NSGlobalDomain.KeyRepeat = 2;
    NSGlobalDomain.NSAutomaticWindowAnimationsEnabled = false; # desable animations
    NSGlobalDomain.NSDocumentSaveNewDocumentsToCloud = false; # iCloud sucks
    NSGlobalDomain.NSStatusItemSpacing = 8; # reduce spacing between status icons in the menu bar. default 12
    NSGlobalDomain.NSWindowShouldDragOnGesture = true; # finally - proper window dragging
    NSGlobalDomain."com.apple.keyboard.fnState" = true; # F1-F12 act as they should
    loginwindow.GuestEnabled = false;
    menuExtraClock.Show24Hour = true;
    menuExtraClock.ShowAMPM = false;
    menuExtraClock.ShowDate = 1;
    menuExtraClock.ShowDayOfMonth = true;
    menuExtraClock.ShowDayOfWeek = true;
    spaces.spans-displays = false;
    universalaccess.reduceMotion = false; # less animations
  };

  security.pam.services.sudo_local.touchIdAuth = true; # Enable sudo authentication with Touch ID

  # programms installed by homebrew
  homebrew = {
    enable = true;
    caskArgs.no_quarantine = true;
    global.brewfile = true;
    masApps = { };
    casks = [
      "1password"
      "1password-cli"
      "antigravity"
      "brave-browser"
      "firefox@developer-edition"
      "microsoft-edge"
      "raycast"
      "telegram"
      "moonlight"
      "notion"
      "obsidian"
      "scroll-reverser"
      "istat-menus"
      "hammerspoon"
      "docker-desktop"
      "vmware-fusion"
      "linearmouse"
      "rectangle"
      "ghostty"
    ];
    taps = [
      "fujiapple852/trippy"
      "d12frosted/emacs-plus"
      "LizardByte/homebrew"
    ];
    brews = [
      "trippy"
      "emacs-plus"
      # "sunshine" it's broken now
    ];
    onActivation = {
      autoUpdate = true;
      upgrade = true;
    };
  };

  nix.package = pkgs.nix;

  # Backward compatibility
  system.stateVersion = 4;
}
