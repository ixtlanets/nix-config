{
  inputs,
  outputs,
  lib,
  config,
  pkgs,
  ...
}:
let
  isLinux = pkgs.stdenv.isLinux;
  gpgPublicKey = builtins.readFile ../../secrets/gpg/public.key;
  gpgPrivateKey = builtins.readFile ../../secrets/gpg/private.key;

  vpn-script = pkgs.writeShellScriptBin "vpn" ''
    #!/usr/bin/env nix-shell
    # gen dns suffix
    DNS_SUFFIX=$(tailscale status --json | jq '.MagicDNSSuffix' | sed 's/"//g')

    # get list of available exit nodes
    EXIT_NODES=$(tailscale status --json | jq '.Peer[] | select(.ExitNodeOption==true) | select(.Online==true) | .DNSName' | sed "s/\.$DNS_SUFFIX\.//g" | sed 's/"//g')



    # add 'None' to the list none option
    EXIT_NODES+="\nNone"
    EXIT_NODES=$(echo -e "$EXIT_NODES")

    SELECTED=$(tailscale status --json | jq '.Peer[] | select(.ExitNode==true) | .DNSName' | sed "s/\.$DNS_SUFFIX\.//g" | sed 's/"//g')

    # if SELECTED is empty, put None there
    if [[ -z "$SELECTED" ]]; then
      SELECTED="None"
    fi

    #let user select exit node with gum
    EXIT_NODE=$(gum choose --selected $SELECTED $EXIT_NODES)
    if [[ "$EXIT_NODE" == "None" ]]; then
      sudo tailscale up --exit-node "" --exit-node-allow-lan-access=false
    else
      sudo tailscale up --exit-node $EXIT_NODE --exit-node-allow-lan-access=true
    fi

  '';
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
in
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

  home.sessionVariables = {
    TZ_LIST = "Europe/London,London;America/New_York,NY;America/Los_Angeles,GR-office";
  };

  home.packages =
    with pkgs;
    [
      ffmpeg
      glow # markdown reader for terminal
      portal # file transfer
      tz # A time zone helper
      imagemagick
      parallel
      nixpkgs-fmt
      nodejs
      bun # better than nodejs and npm
      gam # Google workspace admin cli
      (pkgs.python3.withPackages (
        p: with p; [
          ipython
          jupyter
        ]
      ))
      imgp # fast image resizer
      ffmpegthumbnailer
      mediainfo
      nsxiv
      gnupg
      gum
      pscale
      tat-script
      fd # modern find
      du-dust # modern du
      speedtest-rs # speedtest
      fabric-ai
      codex # AI coding agent by OpenAI
      viu # terminal image viewer
      ast-grep # code structural search

      git-crypt
      git-lfs
      devenv
      _1password-cli
      sshuttle # VPN over ssh
    ]
    ++ (lib.optionals isLinux [
      xdragon
      vpn-script
      tabbed
      openssh
      swayimg
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
    direnv = {
      enable = true;
    };
    zsh = {
      enable = true;
      autosuggestion.enable = true;
      enableCompletion = true;
      defaultKeymap = "emacs";
      syntaxHighlighting.enable = true;
      history = {
        expireDuplicatesFirst = true;
        ignoreDups = true;
      };
      initContent = ''
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
    yazi = {
      enable = true;
      settings = {
        manager = {
          linemode = "size";
        };
        opener = {
          wallpaper = [
            {
              #  `$@` expands to the absolute path(s) of the selected file(s)
              run = "variety --set-wallpaper \"$@\"";
              block = false; # don’t block yazi while the command runs
            }
          ];
          text = [
            {
              run = "nvim \"$@\"";
              block = true;
            }
          ];
          pdf = [
            {
              run = "zathura \"$@\"";
              block = false;
            }
          ];
          office = [
            {
              run = "libreoffice \"$@\"";
              block = false;
            }
          ];
          image = [
            {
              run = "swayimg \"$@\"";
              block = false;
            }
          ];
          video = [
            {
              run = "mpv \"$@\"";
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
              use = "wallpaper";
            }
            {
              name = "*.jpeg";
              use = "wallpaper";
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

  home.activation = {
    importGpgKeys = lib.hm.dag.entryAfter [ "writeBoundary" ] ''
      if ! ${pkgs.gnupg}/bin/gpg --list-secret-keys | grep -q "${config.programs.git.userEmail}"; then
      echo "${gpgPublicKey}" | ${pkgs.gnupg}/bin/gpg --import
      echo "${gpgPrivateKey}" | ${pkgs.gnupg}/bin/gpg --import
      fi
    '';
    setupSsh = lib.hm.dag.entryAfter [ "writeBoundary" ] ''
      # Create .ssh directory with correct permissions
      mkdir -p ~/.ssh
      chmod 700 ~/.ssh

      # Copy and set permissions for private keys
      cp -f ${../../secrets/ssh/id_rsa} ~/.ssh/id_rsa
      chmod 600 ~/.ssh/id_rsa
      cp -f ${../../secrets/ssh/id_rsa_1} ~/.ssh/id_rsa_1
      chmod 600 ~/.ssh/id_rsa_1
      cp -f ${../../secrets/ssh/startspiritup-firebase-adminsdk-o9eey-c7292ac3f8.json} ~/.ssh/startspiritup-firebase-adminsdk-o9eey-c7292ac3f8.json
      chmod 600 ~/.ssh/startspiritup-firebase-adminsdk-o9eey-c7292ac3f8.json

      # Copy public keys
      cp -f ${../../secrets/ssh/id_rsa.pub} ~/.ssh/id_rsa.pub
      cp -f ${../../secrets/ssh/id_rsa_1.pub} ~/.ssh/id_rsa_1.pub
    '';
    clonePasswordStore = lib.hm.dag.entryAfter [ "writeBoundary" ] ''
      if [ ! -d "$HOME/.password-store" ]; then
      PATH="${pkgs.openssh}/bin:${pkgs.git}/bin:${pkgs.git-lfs}/bin:$PATH" ${pkgs.git}/bin/git clone git@github.com:snikulin/.password-store.git "$HOME/.password-store"
      fi
    '';
    cloneOrgStore = lib.hm.dag.entryAfter [ "writeBoundary" ] ''
      if [ ! -d "$HOME/org" ]; then
      PATH="${pkgs.openssh}/bin:${pkgs.git}/bin:${pkgs.git-lfs}/bin:$PATH" ${pkgs.git}/bin/git clone git@github.com:snikulin/org.git "$HOME/org"
      fi
    '';
    closeGitProjects = lib.hm.dag.entryAfter [ "writeBoundary" ] ''
      if [ ! -d "$HOME/pro" ]; then
      mkdir -p "$HOME/pro/GR"
      mkdir -p "$HOME/pro/verbatoria"
      mkdir -p "$HOME/pro/loktar"
      PATH="${pkgs.openssh}/bin:${pkgs.git}/bin:${pkgs.git-lfs}/bin:$PATH" ${pkgs.git}/bin/git clone git@github.com:snikulin/gr-cbhelper.git "$HOME/pro/GR/gr-cbhelper"
      PATH="${pkgs.openssh}/bin:${pkgs.git}/bin:${pkgs.git-lfs}/bin:$PATH" ${pkgs.git}/bin/git clone git@github.com:snikulin/gr-crunchbase-scraper.git "$HOME/pro/GR/gr-crunchbase-scraper"
      PATH="${pkgs.openssh}/bin:${pkgs.git}/bin:${pkgs.git-lfs}/bin:$PATH" ${pkgs.git}/bin/git clone git@github.com:snikulin/gr-firestore.git "$HOME/pro/GR/gr-firestore"
      PATH="${pkgs.openssh}/bin:${pkgs.git}/bin:${pkgs.git-lfs}/bin:$PATH" ${pkgs.git}/bin/git clone git@github.com:snikulin/gr-processor.git "$HOME/pro/GR/gr-processor"
      PATH="${pkgs.openssh}/bin:${pkgs.git}/bin:${pkgs.git-lfs}/bin:$PATH" ${pkgs.git}/bin/git clone git@github.com:snikulin/gr-startups-sight.git "$HOME/pro/GR/gr-startups-sight"
      PATH="${pkgs.openssh}/bin:${pkgs.git}/bin:${pkgs.git-lfs}/bin:$PATH" ${pkgs.git}/bin/git clone git@github.com:snikulin/verbatoria-webapp.git "$HOME/pro/verbatoria/verbatoria-webapp"
      PATH="${pkgs.openssh}/bin:${pkgs.git}/bin:${pkgs.git-lfs}/bin:$PATH" ${pkgs.git}/bin/git clone git@github.com:snikulin/verbatoria_backend.git "$HOME/pro/verbatoria/verbatoria_backend"
      PATH="${pkgs.openssh}/bin:${pkgs.git}/bin:${pkgs.git-lfs}/bin:$PATH" ${pkgs.git}/bin/git clone git@github.com:snikulin/verbatoria_frontend.git "$HOME/pro/verbatoria/verbatoria_frontend"
      PATH="${pkgs.openssh}/bin:${pkgs.git}/bin:${pkgs.git-lfs}/bin:$PATH" ${pkgs.git}/bin/git clone git@github.com:snikulin/verbatoria_full.git "$HOME/pro/verbatoria/verbatoria_full"
      PATH="${pkgs.openssh}/bin:${pkgs.git}/bin:${pkgs.git-lfs}/bin:$PATH" ${pkgs.git}/bin/git clone git@github.com:snikulin/verbatoria_go.git "$HOME/pro/verbatoria/verbatoria_go"
      PATH="${pkgs.openssh}/bin:${pkgs.git}/bin:${pkgs.git-lfs}/bin:$PATH" ${pkgs.git}/bin/git clone git@github.com:snikulin/verbatoria_node.git "$HOME/pro/verbatoria/verbatoria_node"
      PATH="${pkgs.openssh}/bin:${pkgs.git}/bin:${pkgs.git-lfs}/bin:$PATH" ${pkgs.git}/bin/git clone git@github.com:snikulin/detector.git "$HOME/pro/loktar/detector"
      PATH="${pkgs.openssh}/bin:${pkgs.git}/bin:${pkgs.git-lfs}/bin:$PATH" ${pkgs.git}/bin/git clone git@loktar.gitlab.yandexcloud.net:loktar/drone-detector.git "$HOME/pro/loktar/drone-detector"
      fi
    '';
  };
}
