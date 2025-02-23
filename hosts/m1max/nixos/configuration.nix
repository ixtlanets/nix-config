{ config, pkgs, ... }:

{
  nix.settings.experimental-features = [
    "nix-command"
    "flakes"
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
    systemPackages = [ pkgs.coreutils ];
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
    dock.autohide = true; # a bit more space
    dock.autohide-time-modifier = 0.0; # no stupid animation
    dock.mru-spaces = false; # Do not rearrange spaces
    dock.orientation = "right";
    dock.show-recents = false;
    dock.tilesize = 32;
    dock.wvous-bl-corner = 1; # Disable Hot corner action for bottom left corner
    dock.wvous-br-corner = 1; # Disable Hot corner action for bottom right corner
    dock.wvous-tl-corner = 1; # Disable Hot corner action for top left corner
    dock.wvous-tr-corner = 1; # Disable Hot corner action for top right corner
    hitoolbox.AppleFnUsageType = "Do Nothing"; # Do nothing on "fn" key press
    NSGlobalDomain.AppleShowAllExtensions = true;
    NSGlobalDomain.InitialKeyRepeat = 14;
    NSGlobalDomain.KeyRepeat = 2;
    loginwindow.GuestEnabled = false;
    menuExtraClock.Show24Hour = true;
    menuExtraClock.ShowAMPM = false;
    menuExtraClock.ShowDate = 1;
    menuExtraClock.ShowDayOfMonth = true;
    menuExtraClock.ShowDayOfWeek = true;
    spaces.spans-displays = true; # one space spans across all physical displays. aerospace recommend this setting
    universalaccess.reduceMotion = false; # less animations
  };

  security.pam.enableSudoTouchIdAuth = true; # Enable sudo authentication with Touch ID

  # programms installed by homebrew
  homebrew = {
    enable = true;
    caskArgs.no_quarantine = true;
    global.brewfile = true;
    masApps = { };
    casks = [
      "1password"
      "1password-cli"
      "brave-browser"
      "firefox-developer-edition"
      "microsoft-edge"
      "raycast"
      "telegram"
      "moonlight"
      "notion"
      "obsidian"
      "scroll-reverser"
      "istat-menus"
      "hammerspoon"
      "docker"
      "vmware-fusion"
      "linearmouse"
      "rectangle"
      "ghostty"
      "nikitabobko/tap/aerospace"
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
  };

  nix.package = pkgs.nix;

  # Backward compatibility
  system.stateVersion = 4;
}
