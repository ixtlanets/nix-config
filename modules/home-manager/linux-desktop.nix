{ pkgs, ... }:
let
  lmstudio = pkgs.unstable.lmstudio;
  convertChatgptImagesToJpg = pkgs.writeShellScript "convert-chatgpt-images-to-jpg" ''
    set -u

    downloads_dir="$HOME/Downloads"
    state_dir="$HOME/.local/state"
    log_file="$state_dir/convert-chatgpt-images-to-jpg.log"
    now_epoch="$(${pkgs.coreutils}/bin/date +%s)"
    max_age_seconds=300

    ${pkgs.coreutils}/bin/mkdir -p "$state_dir"

    log() {
      printf '%s %s\n' "$(${pkgs.coreutils}/bin/date '+%Y-%m-%d %H:%M:%S')" "$*" >> "$log_file"
    }

    converted=0
    skipped=0
    failed=0

    shopt -s nullglob
    for png_path in "$downloads_dir"/ChatGPT\ Image*.png; do
      jpg_path="''${png_path%.png}.jpg"
      tmp_jpg="$jpg_path.tmp"

      if [[ -e "$jpg_path" ]]; then
        skipped=$((skipped + 1))
        continue
      fi

      created_epoch="$(${pkgs.coreutils}/bin/stat -c %W "$png_path" 2>/dev/null || printf '0')"
      if [[ "$created_epoch" -le 0 ]]; then
        created_epoch="$(${pkgs.coreutils}/bin/stat -c %Y "$png_path" 2>/dev/null || printf '0')"
      fi

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

      if ${pkgs.imagemagick}/bin/magick "$png_path" -quality 90 "$tmp_jpg" >/dev/null 2>&1; then
        if ${pkgs.coreutils}/bin/mv -f -- "$tmp_jpg" "$jpg_path" && ${pkgs.coreutils}/bin/rm -- "$png_path"; then
          converted=$((converted + 1))
          log "converted: $png_path -> $jpg_path"
        else
          failed=$((failed + 1))
          log "failed: converted but could not replace output or delete source: $png_path"
        fi
      else
        failed=$((failed + 1))
        ${pkgs.coreutils}/bin/rm -f -- "$tmp_jpg"
        log "failed: ImageMagick conversion failed: $png_path"
      fi
    done

    if [[ "$converted" -gt 0 || "$failed" -gt 0 ]]; then
      log "summary: converted=$converted skipped=$skipped failed=$failed"
    fi
  '';
in
{

  home.packages = with pkgs; [
    browserpass
    google-chrome
    telegram-desktop
    moonlight-qt
    nerd-fonts.ubuntu
    nerd-fonts.ubuntu-mono
    nerd-fonts.ubuntu-sans
    nerd-fonts.sauce-code-pro
    nerd-fonts.hack
    monaspace
    variety
    prismlauncher
    zathura
    brightnessctl
    pamixer
    wireplumber
    mpv
    liberation_ttf
    font-awesome
    zoom-us
    obsidian
    wl-clipboard
    vscode
    pkgs.unstable.libreoffice-qt6-fresh
    lmstudio
    google-antigravity
    code-cursor-fhs
    papirus-icon-theme
    kora-icon-theme
    dotool
    wtype
    voxtype-onnx
    vulkan-tools
  ];

  catppuccin.flavor = "mocha";
  catppuccin.enable = true;
  catppuccin.gtk.icon.enable = false;
  catppuccin.nvim.enable = false;
  catppuccin.alacritty.enable = true;

  programs = {
    alacritty = {
      enable = true;
      settings = {
        env.TERM = "xterm-256color";
        font = {
          normal.family = "Hack Nerd Font Mono";
          size = 14;
        };
      };
    };
    zed-editor = {
      enable = true;
    };
    browserpass = {
      enable = true;
      browsers = [
        "brave"
        "firefox"
        "chromium"
        "chrome"
      ];
    };

    firefox = {
      enable = true;
      policies.ExtensionSettings = {
        "uBlock0@raymondhill.net" = {
          installation_mode = "force_installed";
          install_url = "https://addons.mozilla.org/firefox/downloads/latest/ublock-origin/latest.xpi";
        };
        "{d634138d-c276-4fc8-924b-40a0ea21d284}" = {
          installation_mode = "force_installed";
          install_url = "https://addons.mozilla.org/firefox/downloads/latest/1password-x-password-manager/latest.xpi";
        };
        "sponsorBlocker@ajay.app" = {
          installation_mode = "force_installed";
          install_url = "https://addons.mozilla.org/firefox/downloads/latest/sponsorblock/latest.xpi";
        };
        "{9fda17be-849d-4f5b-a326-28d25f0f6d29}" = {
          installation_mode = "force_installed";
          install_url = "https://addons.mozilla.org/firefox/downloads/latest/utm-tracking-token-stripper/latest.xpi";
        };
        "deArrow@ajay.app" = {
          installation_mode = "force_installed";
          install_url = "https://addons.mozilla.org/firefox/downloads/latest/dearrow/latest.xpi";
        };
        "{2662ff67-b302-4363-95f3-b050218bd72c}" = {
          installation_mode = "force_installed";
          install_url = "https://addons.mozilla.org/firefox/downloads/latest/untrap-for-youtube/latest.xpi";
        };
        "extension@tabliss.io" = {
          installation_mode = "force_installed";
          install_url = "https://addons.mozilla.org/firefox/downloads/latest/tabliss/latest.xpi";
        };
        "jid1-KKzOGWgsW3Ao4Q@jetpack" = {
          installation_mode = "force_installed";
          install_url = "https://addons.mozilla.org/firefox/downloads/latest/i-dont-care-about-cookies/latest.xpi";
        };
        "enhancerforyoutube@maximerf.addons.mozilla.org" = {
          installation_mode = "force_installed";
          install_url = "https://addons.mozilla.org/firefox/downloads/latest/enhancer-for-youtube/latest.xpi";
        };
      };
    };

    chromium = {
      enable = true;
      extensions = [
        { id = "ddkjiahejlhfcafbddmgiahcphecmpfh"; } # ublock origin lite, since Google broken proper extensions
        { id = "aeblfdkhhhdcdjpifhhbdiojplfjncoa"; } # 1Password
        { id = "mnjggcdmjocbbbhaepdhchncahnbgone"; } # SponsorBlock for YouTube - Skip Sponsorships
        { id = "enamippconapkdmgfgjchkhakpfinmaj"; } # DeArrow. dearrow.ajay.app
        { id = "enboaomnljigfhfjfoalacienlhjlfil"; } # Untrap - Remove YouTube Suggestions
        { id = "hipekcciheckooncpjeljhnekcoolahp"; } # Tabliss - A Beautiful New Tab
        { id = "edibdbjcniadpccecjdfdjjppcpchdlm"; } # I still don't care about cookies
        { id = "ponfpcnoihfmfllpaingbgckeeldkhle"; } # Enhancer for YouTube
      ];
    };
    brave = {
      enable = true;
      extensions = [
        { id = "cjpalhdlnbpafiamejdnhcphjbkeiagm"; } # ublock origin
        { id = "aeblfdkhhhdcdjpifhhbdiojplfjncoa"; } # 1Password
        { id = "mnjggcdmjocbbbhaepdhchncahnbgone"; } # SponsorBlock for YouTube - Skip Sponsorships
        { id = "kcpnkledgcbobhkgimpbmejgockkplob"; } # Tracking Token Stripper
        { id = "enamippconapkdmgfgjchkhakpfinmaj"; } # DeArrow. dearrow.ajay.app
        { id = "enboaomnljigfhfjfoalacienlhjlfil"; } # Untrap - Remove YouTube Suggestions
        { id = "hipekcciheckooncpjeljhnekcoolahp"; } # Tabliss - A Beautiful New Tab
        { id = "edibdbjcniadpccecjdfdjjppcpchdlm"; } # I still don't care about cookies
        { id = "ponfpcnoihfmfllpaingbgckeeldkhle"; } # Enhancer for YouTube
        {
          id = "dcpihecpambacapedldabdbpakmachpb";
          updateUrl = "https://raw.githubusercontent.com/iamadamdev/bypass-paywalls-chrome/master/src/updates/updates.xml";
        }
      ];
      commandLineArgs = [ "--disable-features=WaylandWpColorManagerV1" ]; # fix for crash on hyprland
    };
    google-chrome = {
      enable = true;
    };

    obs-studio = {
      enable = true;
      plugins = with pkgs.obs-studio-plugins; [
        wlrobs
        obs-backgroundremoval
        obs-pipewire-audio-capture
      ];
    };
  };

  xresources.extraConfig = builtins.readFile ../../dotfiles/Xresources;
  xdg.configFile."voxtype/config.toml".text = ''
    state_file = "auto"
    engine = "parakeet"

    [hotkey]
    enabled = true
    key = "RIGHTALT"

    [audio]
    device = "default"
    sample_rate = 16000
    max_duration_secs = 60

    [parakeet]
    model = "parakeet-tdt-0.6b-v3"
    language = ["en", "ru"]

    [text]
    spoken_punctuation = true

    [text.replacements]
    "chrome dev tools" = "Chrome DevTools"
    "chrome left tools" = "Chrome DevTools"
    "dev tools" = "DevTools"
    "devtulz" = "DevTools"
    "voxtype" = "Voxtype"
    "вокстайп" = "Voxtype"
    "и2и" = "e2e"
    "комит" = "commit"
    "комита" = "commit"
    "комитом" = "commit"
    "комиту" = "commit"
    "никс оэс" = "NixOS"
    "хром" = "Chrome"
    "хромиум" = "chromium"
    "юайуикс" = "UI/UX"

    [output]
    mode = "paste"
    paste_keys = "ctrl+shift+v"
    restore_clipboard = true

    [output.notification]
    on_transcription = true

    [meeting]
    enabled = true
  '';
  xdg.configFile."variety/variety.conf".text = builtins.readFile ../../dotfiles/variety.conf;
  xdg.configFile."variety/pluginconfig/quotes/quotes.txt".text =
    builtins.readFile ../../dotfiles/quotes.txt;
  home.file."scripts/set_wallpaper" = {
    text = builtins.readFile scripts/set_wallpaper;
    executable = true;
  };

  systemd.user.paths.convert-chatgpt-images-to-jpg = {
    Unit.Description = "Watch for ChatGPT image downloads";
    Path = {
      PathChanged = "%h/Downloads";
      PathExistsGlob = "%h/Downloads/ChatGPT Image*.png";
      Unit = "convert-chatgpt-images-to-jpg.service";
    };
    Install.WantedBy = [ "default.target" ];
  };

  systemd.user.services.convert-chatgpt-images-to-jpg = {
    Unit.Description = "Convert recent ChatGPT PNG downloads to JPG";
    Service = {
      Type = "oneshot";
      ExecStart = "${convertChatgptImagesToJpg}";
    };
  };

  gtk = {
    enable = true;
    colorScheme = "dark";
    theme = {
      name = "catppuccin-mocha-blue-standard";
      package = pkgs.catppuccin-gtk.override {
        accents = [ "blue" ];
        size = "standard";
        variant = "mocha";
      };
    };
    iconTheme = {
      name = "kora";
      package = pkgs.kora-icon-theme;
    };
    gtk4.theme = {
      name = "catppuccin-mocha-blue-standard";
      package = pkgs.catppuccin-gtk.override {
        accents = [ "blue" ];
        size = "standard";
        variant = "mocha";
      };
    };
  };
  qt.enable = true;
  qt.style.name = "kvantum";
  qt.platformTheme.name = "kvantum";
  home.pointerCursor = {
    name = "Bibata-Original-Ice";
    package = pkgs.bibata-cursors;
    gtk.enable = true;
    x11.enable = true;
    x11.defaultCursor = "Bibata-Original-Ice";
    size = 24;
  };
}
