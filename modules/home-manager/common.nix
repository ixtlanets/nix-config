{ inputs, outputs, lib, config, pkgs, niknvim, ... }: 
let
  isLinux = pkgs.stdenv.isLinux;
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
    pscale
    tat-script
    fd # modern find
    du-dust # modern du
    speedtest-rs # speedtest

    git-crypt
  ] ++ (lib.optionals isLinux [
    tabbed
  ]);

  # Enable home-manager and git
  programs = {
    home-manager.enable = true;
    gpg.enable = true;
    bat = {
      enable = true;
    };
    ripgrep = {
      enable = true;
    };
    eza = {
      enable = true;
    };
    ncspot = {
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
      autosuggestion.enable = true;
      enableCompletion = true;
      syntaxHighlighting.enable = true;
      history = {
        expireDuplicatesFirst = true;
        ignoreDups = true;
      };
      initExtra = ''
        export PATH="$HOME/.local/bin:$HOME/go/bin:$PATH"
      '';
    };
    fzf = {
      enable = true;
    };
    password-store = {
      enable = true;
      package = pkgs.pass.withExtensions (exts: [ 
        exts.pass-otp 
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
        "output" = "~/Video/YouTube/%(uploader)s/%(title)s.%(ext)s";
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
      settings = {
        opener = {
          text = [
          {
            exec = "nvim \"$@\"";
            block = true;
          }
          ];
          pdf = [
          {
            exec = "zathura \"$@\"";
            block = false;
          }
          ];
          office = [
          {
            exec = "libreoffice \"$@\"";
            block = false;
          }
          ];
          image = [
          {
            exec = "swayimg \"$@\"";
            block = false;
          }
          ];
          video = [
          {
            exec = "mpv \"$@\"";
            block = false;
          }
          ];
        };
        open = {
          rules = [
          {
            name = "*.json";
            use = "text";
          }
          {
            name = "*.cpp";
            use = "text";
          }
          {
            name = "*.lua";
            use = "text";
          }
          {
            name = "*.toml";
            use = "text";
          }
          {
            name = "*.yaml";
            use = "text";
          }
          {
            name = "*.c";
            use = "text";
          }
          {
            name = "*.ts";
            use = "text";
          }
          {
            name = "*.nix";
            use = "text";
          }
          {
            name = "*.md";
            use = "text";
          }
          {
            name = "*.js";
            use = "text";
          }
          {
            name = "*.jsx";
            use = "text";
          }
          {
            name = "*.tsx";
            use = "text";
          }
          {
            name = "*.pdf";
            use = "pdf";
          }
          {
            name = "*.docx";
            use = "office";
          }
          {
            name = "*.pptx";
            use = "office";
          }
          {
            name = "*.xlsx";
            use = "office";
          }
          {
            name = "*.odt";
            use = "office";
          }
          {
            name = "*.png";
            use = "image";
          }
          {
            name = "*.jpg";
            use = "image";
          }
          {
            name = "*.jpeg";
            use = "image";
          }
          {
            name = "*.gif";
            use = "image";
          }
          {
            name = "*.svg";
            use = "image";
          }
          {
            name = "*.bmp";
            use = "image";
          }
          {
            name = "*.tiff";
            use = "image";
          }
          {
            name = "*.tif";
            use = "image";
          }
          {
            name = "*.webp";
            use = "image";
          }
          {
            name = "*.heic";
            use = "image";
          }
          {
            name = "*.heif";
            use = "image";
          }
          {
            name = "*.mp4";
            use = "video";
          }
          {
            name = "*.mkv";
            use = "video";
          }
          {
            name = "*.webm";
            use = "video";
          }
          {
            name = "*.avi";
            use = "video";
          }
          {
            name = "*.mov";
            use = "video";
          }
          {
            name = "*.wmv";
            use = "video";
          }
          {
            name = "*.flv";
            use = "video";
          }
          {
            name = "*.m4v";
            use = "video";
          }
          {
            name = "*.mpg";
            use = "video";
          }
          {
            name = "*.mpeg";
            use = "video";
          }
          ];
        };
      };
    };
  };

  home.shellAliases = {
    gst = "git status";
  };
}
