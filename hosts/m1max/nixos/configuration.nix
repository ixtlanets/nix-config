{
  pkgs,
  inputs,
  ...
}:

let
  floxPkg = inputs.flox.packages.${pkgs.stdenv.hostPlatform.system}.default;
  convertChatgptImagesToJpg = pkgs.writeShellScript "convert-chatgpt-images-to-jpg" ''
    set -u

    downloads_dir="$HOME/Downloads"
    log_file="$HOME/Library/Logs/convert-chatgpt-images-to-jpg.log"
    now_epoch="$(/bin/date +%s)"
    max_age_seconds=300

    /bin/mkdir -p "$(/usr/bin/dirname "$log_file")"

    log() {
      printf '%s %s\n' "$(/bin/date '+%Y-%m-%d %H:%M:%S')" "$*" >> "$log_file"
    }

    converted=0
    skipped=0
    failed=0

    shopt -s nullglob
    for png_path in "$downloads_dir"/ChatGPT\ Image*.png; do
      jpg_path="''${png_path%.png}.jpg"

      if [[ -e "$jpg_path" ]]; then
        skipped=$((skipped + 1))
        continue
      fi

      created_epoch="$(/usr/bin/stat -f %B "$png_path" 2>/dev/null || printf '0')"
      if [[ "$created_epoch" -le 0 ]]; then
        skipped=$((skipped + 1))
        log "skip: could not read creation time: $png_path"
        continue
      fi

      age_seconds=$((now_epoch - created_epoch))
      if [[ "$age_seconds" -lt 0 || "$age_seconds" -gt "$max_age_seconds" ]]; then
        skipped=$((skipped + 1))
        continue
      fi

      if /usr/bin/sips -s format jpeg -s formatOptions 90 "$png_path" --out "$jpg_path" >/dev/null 2>&1; then
        if /bin/rm -- "$png_path"; then
          converted=$((converted + 1))
          log "converted: $png_path -> $jpg_path"
        else
          failed=$((failed + 1))
          log "failed: converted but could not delete source: $png_path"
        fi
      else
        failed=$((failed + 1))
        /bin/rm -f -- "$jpg_path"
        log "failed: sips conversion failed: $png_path"
      fi
    done

    if [[ "$converted" -gt 0 || "$failed" -gt 0 ]]; then
      log "summary: converted=$converted skipped=$skipped failed=$failed"
    fi
  '';
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
  nix.settings.trusted-users = [ "nik" ];

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

  security.pam.services.sudo_local = {
    enable = true;
    touchIdAuth = true; # Enable sudo authentication with Touch ID
    reattach = true; # This fixes Touch ID for sudo not working inside tmux and screen.
  };

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
      "codex"
    ];
    taps = [
      "fujiapple852/trippy"
      "d12frosted/emacs-plus"
      "LizardByte/homebrew"
    ];
    brews = [
      "trippy"
      "emacs-plus"
      "llama.cpp"
      "openclaw-cli"
      # "sunshine" it's broken now
    ];
    onActivation = {
      autoUpdate = true;
      upgrade = true;
    };
  };

  launchd.user.agents.llama-server = {
    path = [ "/opt/homebrew/bin" ];
    serviceConfig = {
      Label = "ai.llama.server";
      KeepAlive = true;
      ProcessType = "Background";
      ProgramArguments = [
        "/opt/homebrew/bin/llama-server"
        "-hf"
        "unsloth/Qwen3.6-35B-A3B-MTP-GGUF"
        "--host"
        "0.0.0.0"
        "--port"
        "8080"
        "--flash-attn"
        "on"
        "--spec-type"
        "draft-mtp"
        "--spec-draft-n-max"
        "3"
        "--reasoning"
        "off"
        "--chat-template-kwargs"
        ''{"enable_thinking": false}''
      ];
      RunAtLoad = true;
      StandardErrorPath = "/Users/nik/Library/Logs/llama-server.log";
      StandardOutPath = "/Users/nik/Library/Logs/llama-server.log";
      WorkingDirectory = "/Users/nik";
    };
  };

  launchd.user.agents.convert-chatgpt-images-to-jpg = {
    serviceConfig = {
      Label = "com.nik.convert-chatgpt-images-to-jpg";
      ProgramArguments = [ "${convertChatgptImagesToJpg}" ];
      RunAtLoad = true;
      StandardErrorPath = "/Users/nik/Library/Logs/convert-chatgpt-images-to-jpg.launchd.err.log";
      StandardOutPath = "/Users/nik/Library/Logs/convert-chatgpt-images-to-jpg.launchd.out.log";
      WatchPaths = [ "/Users/nik/Downloads" ];
    };
  };

  # nix 2.31.2+1 fails the nix-shell shebang functional test on aarch64-darwin;
  # stick to the previous release until upstream fixes the regression.
  nix.package = pkgs.nixVersions.nix_2_30;

  # Backward compatibility
  system.stateVersion = 4;
}
