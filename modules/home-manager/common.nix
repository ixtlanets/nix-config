{ inputs, outputs, lib, config, pkgs, niknvim, ... }: 
let
tat-script = pkgs.writeShellScriptBin "tat" ''
#!/bin/sh
#
# Attach or create tmux session named the same as current directory.

path_name="$(basename "$PWD" | tr . -)"
session_name=''${1-$path_name}

not_in_tmux() {
  [ -z "$TMUX" ]
}

session_exists() {
  tmux has-session -t "=$session_name"
}

create_detached_session() {
  (TMUX="" tmux new-session -Ad -s "$session_name")
}

create_if_needed_and_attach() {
  if not_in_tmux; then
    tmux new-session -As "$session_name"
  else
    if ! session_exists; then
      create_detached_session
    fi
    tmux switch-client -t "$session_name"
  fi
}

create_if_needed_and_attach
'';
in {
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
    #niknvim.packages."${system}".default
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
    pscale
    tat-script
  ];

  # Enable home-manager and git
  programs = {
    home-manager.enable = true;
    gpg.enable = true;
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
    yazi = {
      enable = true;
    };
  };

  services.gpg-agent = {
    enable = true;
    enableSshSupport = true;
    pinentryFlavor = "qt"; # Hyprland/Wayland
  };

  home.shellAliases = {
    gst = "git status";
  };
}
