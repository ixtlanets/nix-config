{ config, pkgs, ... }:

{
  nix.settings.experimental-features = [ "nix-command" "flakes" ];

  networking.hostName = "m1max"; # Define your hostname.

  # Set your time zone.
  time.timeZone = "Europe/Moscow";

  programs.zsh.enable = true;

  users.users.nik = {
    home = "/Users/nik";
  };

  environment = {
    shells = with pkgs; [ bash zsh ];
    loginShell = pkgs.zsh;
    systemPackages = [ pkgs.coreutils ];
    systemPath = [ "/opt/homebrew/bin" ];
    pathsToLink = [ "/Applications" ];
  };

  # Keyboard setttings
  system.keyboard.enableKeyMapping = true;
  system.keyboard.remapCapsLockToEscape = true;

  # Fonts
  fonts.fontDir.enable = true; # DANGER
  fonts.fonts = [ (pkgs.nerdfonts.override { fonts = [ 
    "CascadiaCode"
    "DejaVuSansMono"
    "DroidSansMono"
    "FiraCode"
    "FiraMono"
    "Hack"
    "Inconsolata"
    "Iosevka"
    "JetBrainsMono"
    "Meslo"
    "Noto"
    "RobotoMono"
    "SourceCodePro"
    "Ubuntu"
    "UbuntuMono"
  ]; }) ];

  # mac defaults
  system.defaults = {
    finder.AppleShowAllExtensions = true;
    finder._FXShowPosixPathInTitle = true;
    finder.CreateDesktop = false;
    dock.autohide = true;
    NSGlobalDomain.AppleShowAllExtensions = true;
    NSGlobalDomain.InitialKeyRepeat = 14;
    NSGlobalDomain.KeyRepeat = 2;
  };

  # programms installed by homebrew
  homebrew = {
    enable = true;
    caskArgs.no_quarantine = true;
    global.brewfile = true;
    masApps = { };
    casks = [
      "raycast"
      "amethyst"
      "telegram"
      "moonlight"
      "notion"
      "obsidian"
      "scroll-reverser"
      "istat-menus" 
      "hammerspoon"
      "docker"
      "vmware-fusion"
    ];
    taps = [ "fujiapple852/trippy" ];
    brews = [ "trippy" ];
  };

  # Auto upgrade nix package and the daemon service.
  services.nix-daemon.enable = true;
  nix.package = pkgs.nix;

  # Backward compatibility
  system.stateVersion = 4;
}
