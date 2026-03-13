{
  outputs,
  inputs,
  lib,
  config,
  pkgs,
  ...
}:
let
  isLinux = pkgs.stdenv.isLinux;
  isDarwin = pkgs.stdenv.isDarwin;
  floxPkg = inputs.flox.packages.${pkgs.stdenv.hostPlatform.system}.default;
  gpgPublicKey = builtins.readFile ../../secrets/gpg/public.key;
  gpgPrivateKey = builtins.readFile ../../secrets/gpg/private.key;
  gpgOwnerTrust = lib.removeSuffix "\n" (builtins.readFile ../../secrets/gpg/ownertrust.txt);

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
  imports = [
    ./fix-text.nix
    ./ips-script.nix
    ./yt-dlp-helper.nix
    ./yt-script.nix
  ];
  nixpkgs = {
    # You can add overlays here
    overlays = [
      # Add overlays your own flake exports (from overlays and pkgs dir):
      outputs.overlays.additions
      outputs.overlays.modifications
      outputs.overlays.unstable-packages
      outputs.overlays.antigravity
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
    TZ_LIST = "Europe/London,London;America/New_York,NY;America/Los_Angeles,GR-office;Europe/Berlin,Berlin";
  };

  home.packages =
    with pkgs;
    [
      floxPkg
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
      dust # modern du
      speedtest-rs # speedtest
      fabric-ai
    ]
    ++ lib.optionals (!isDarwin) [
      qwen-code # AI coding agent by Qwen
      codex # AI coding agent by OpenAI
      codebuddy-code # Tencent AI coding tool
    ]
    ++ [
      specify-cli # GitHub Spec Kit CLI for Spec-Driven Development
      viu # terminal image viewer
      ast-grep # code structural search

      git-crypt
      git-lfs
      devenv
      devcontainer # work with vscode devcontainers without vscode itself
      _1password-cli
      sshuttle # VPN over ssh
      cachix
    ]
    ++ (lib.optionals isLinux [
      gemini-cli
      dragon-drop
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
      lfs.enable = true;
      settings = {
        user.email = "snikulin@gmail.com";
        user.name = "Sergey Nikulin";
        init.defaultBranch = "master";
      };
    };
    diff-so-fancy = {
      enable = true;
      enableGitIntegration = true;
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
      package = pkgs.pass.withExtensions (
        exts:
        [
          exts.pass-otp
          exts.pass-genphrase
        ]
        ++ lib.optionals (!pkgs.stdenv.isDarwin) [ exts.pass-import ]
      );
      settings = {
        PASSWORD_STORE_DIR = "$HOME/.password-store";
      };
    };
    yt-dlp = {
      enable = true;
      settings = {
        "cookies-from-browser" = "brave";
        "output" = "~/Videos/YouTube/%(uploader)s/%(title)s.%(ext)s";
        "format" = "bv*[height<=1080]+ba/b[height<=1080]/b";
      };
    };
    yazi = {
      enable = true;
      shellWrapperName = "yy";
      settings = {
        mgr = {
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
              run = "nsxiv \"$@\"";
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
    opencode = {
      enable = true;
      commands = ../../dotfiles/opencode/commands;
      skills = ../../dotfiles/opencode/skills;
      settings = {
        permission = {
          playwright_browser_install = "deny";
        };
        mcp = {
          figma = {
            enabled = true;
            type = "remote";
            url = "https://mcp.figma.com/mcp";
          };

          vercel = {
            enabled = true;
            type = "remote";
            url = "https://mcp.vercel.com";
          };
          chrome-devtools = {
            type = "local";
            command = [
              "bunx"
              "chrome-devtools-mcp@latest"
              "--browser-url=http://127.0.0.1:9222"
            ];
          };
          playwright = {
            enabled = true;
            type = "local";
            command = [
              "npx"
              "@playwright/mcp@latest"
              "--extension"
            ];
            environment = {
              PLAYWRIGHT_MCP_EXTENSION_TOKEN = "{env:PLAYWRIGHT_MCP_EXTENSION_TOKEN}";
            };
          };
        };
      };
    };
  };

  xdg.configFile."opencode/tui.json" = {
    text = builtins.toJSON {
      "$schema" = "https://opencode.ai/tui.json";
      theme = "catppuccin";
    };
  };
  xdg.configFile."opencode/AGENTS.md".text = ''
    When using Playwright MCP, prefer the existing browser session through the Playwright MCP Bridge extension.
    Do not install browsers or start a separate Playwright-managed browser unless I explicitly ask.
    Assume authenticated browser work should happen in my existing Brave profile/session.
  '';

  home.shellAliases = {
    gst = "git status";
  };

  home.activation = {
    importGpgKeys = lib.hm.dag.entryAfter [ "writeBoundary" ] ''
      if ! ${pkgs.gnupg}/bin/gpg --list-secret-keys | grep -q "${config.programs.git.settings.user.email}"; then
        echo "${gpgPublicKey}" | ${pkgs.gnupg}/bin/gpg --import
        echo "${gpgPrivateKey}" | ${pkgs.gnupg}/bin/gpg --import
      fi

      if [ -n "${gpgOwnerTrust}" ]; then
        printf '%s\n' "${gpgOwnerTrust}" | ${pkgs.gnupg}/bin/gpg --import-ownertrust
      fi
    '';
    setupSsh = lib.hm.dag.entryAfter [ "writeBoundary" ] ''
      # Create .ssh directory with correct permissions
      mkdir -p ~/.ssh
      chmod 700 ~/.ssh
      touch ~/.ssh/known_hosts
      chmod 600 ~/.ssh/known_hosts

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

      if ! ${pkgs.gnugrep}/bin/grep -q '^github.com ' ~/.ssh/known_hosts 2>/dev/null; then
        ${pkgs.openssh}/bin/ssh-keyscan github.com >> ~/.ssh/known_hosts 2>/dev/null || \
          echo "warning: failed to fetch github.com host key" >&2
      fi
    '';
    clonePasswordStore = lib.hm.dag.entryAfter [ "setupSsh" ] ''
      if [ ! -d "$HOME/.password-store" ]; then
      export PATH="${pkgs.openssh}/bin:${pkgs.git}/bin:${pkgs.git-lfs}/bin:$PATH"
      export GIT_SSH_COMMAND='${pkgs.openssh}/bin/ssh -o StrictHostKeyChecking=accept-new'
      ${pkgs.git}/bin/git clone git@github.com:snikulin/.password-store.git "$HOME/.password-store" || \
        echo "warning: failed to clone $HOME/.password-store" >&2
      fi
    '';
    cloneOrgStore = lib.hm.dag.entryAfter [ "setupSsh" ] ''
      if [ ! -d "$HOME/org" ]; then
      export PATH="${pkgs.openssh}/bin:${pkgs.git}/bin:${pkgs.git-lfs}/bin:$PATH"
      export GIT_SSH_COMMAND='${pkgs.openssh}/bin/ssh -o StrictHostKeyChecking=accept-new'
      ${pkgs.git}/bin/git clone git@github.com:snikulin/org.git "$HOME/org" || \
        echo "warning: failed to clone $HOME/org" >&2
      fi
    '';
    closeGitProjects = lib.hm.dag.entryAfter [ "setupSsh" ] ''
      if [ ! -d "$HOME/pro" ]; then
      export PATH="${pkgs.openssh}/bin:${pkgs.git}/bin:${pkgs.git-lfs}/bin:$PATH"
      export GIT_SSH_COMMAND='${pkgs.openssh}/bin/ssh -o StrictHostKeyChecking=accept-new'

      clone_warn() {
        local repo="$1"
        local dest="$2"

        if [ -d "$dest" ]; then
          return 0
        fi

        ${pkgs.git}/bin/git clone "$repo" "$dest" || \
          echo "warning: failed to clone $repo into $dest" >&2
      }

      mkdir -p "$HOME/pro/GR"
      mkdir -p "$HOME/pro/verbatoria"
      mkdir -p "$HOME/pro/loktar"
      clone_warn git@github.com:snikulin/gr-cbhelper.git "$HOME/pro/GR/gr-cbhelper"
      clone_warn git@github.com:snikulin/gr-crunchbase-scraper.git "$HOME/pro/GR/gr-crunchbase-scraper"
      clone_warn git@github.com:snikulin/gr-firestore.git "$HOME/pro/GR/gr-firestore"
      clone_warn git@github.com:snikulin/gr-processor.git "$HOME/pro/GR/gr-processor"
      clone_warn git@github.com:snikulin/gr-startups-sight.git "$HOME/pro/GR/gr-startups-sight"
      clone_warn git@github.com:snikulin/verbatoria-webapp.git "$HOME/pro/verbatoria/verbatoria-webapp"
      clone_warn git@github.com:snikulin/verbatoria_backend.git "$HOME/pro/verbatoria/verbatoria_backend"
      clone_warn git@github.com:snikulin/verbatoria_frontend.git "$HOME/pro/verbatoria/verbatoria_frontend"
      clone_warn git@github.com:snikulin/verbatoria_full.git "$HOME/pro/verbatoria/verbatoria_full"
      clone_warn git@github.com:snikulin/verbatoria_go.git "$HOME/pro/verbatoria/verbatoria_go"
      clone_warn git@github.com:snikulin/verbatoria_node.git "$HOME/pro/verbatoria/verbatoria_node"
      fi
    '';
  };
}
