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
  sshAuthorizedKeys = [
    "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQC35qP3UeDJNWzN1ux5FY6Mnsj7KLAmRRt254vjz1Ry5SNwdLE1VhVPVnmIufyKWK5/z6g8NiPvFxXzAyKCitpSS6ahYQjKCXS9b5P3C+FPLcwcy1Ge54Fdu1qGzTeElbIm86+MSA1aQgwbzVfHQYl/TLBk7QVTJ5SdQgdBe7w3tt4hkQMhsqTue6FKF0sTF3xMcKf8B/CSmYHgFiVZsiqg+hb8sYBogIc5vsFlNfxg14UMriGh6/wOvNvZIn7IwgGB2tKGCEtS4p9PL7Vd+LHYUgwta2a/KXgH3xQEuCKDwGPJWpE4kkbSr1SNdQuGZP3Ry9Ta5TMIEgQ8n0mAD9lR nik@msi-ubuntu"
    "ssh-rsa AAAAB3NzaC1yc2EAAAABJQAAAQEAtj2ANdOntRVwWXdMm9FWu2fwDZNH2uEJH+vI37AfPwlmITtxBsOCM9/CYK/wkQa2elfkgkRYqvww0IlwCzI9/88t9YX7CWZU7z/P8ISufNL5VUOfiu15712CJjieauLOzTbAvyFvPhhqTkOpk/Fe1Mi1kFVaBlLqZjHsgokViACOmi+P06XFj0Bl//zAYvqC7mFSRGKDjmicW6vnUxShH6r4QQJv9J2z4KrDHs1ZWUOyWabqaVR4qD/vuGg2kYF/J1YaLKnNQGVNVtSmsaDbwTmev5dPKpZIxgRzl+MyaHDaCCxnzp6dHnjnlP8cfFW55t3Aea5JQCW8vtRrrwKExQ=="
    "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQCgv72CRql2CHmORIPFv4bgLNbdWQbgKbb4VOHqIBnoWddXi1PfoDuhesKrLwr+tvuNcOVzdPo69nh6NhXMsOW3it7FHeEsZ9ADH8W6PiZyEItDvTtrI6j6776ZGsn+pJ0Mj+qP4fZrSkmdd13tiKiigkX5Sif04vlTDGyQiL8zVOiigEO0UIUfTlw45KrE8/iqVnCoVzcaVqQ7QjNUOhGeiKihoIcyco++XiS1Qs2nw8oSvXphQ6KGjGMq1adGl7+4HEYJgkjN0dQqfkZzZtY5TfwKOFGKofj/TRP+pntBbl8RhtBwPpI7lbEQljv715PwYgAHVYhWuOlBQhskGz5L nik@ubuntu-server"
  ];
  sshAuthorizedKeysFile = pkgs.writeText "authorized_keys" (
    lib.concatStringsSep "\n" sshAuthorizedKeys + "\n"
  );

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
    EXIT_NODE=$(gum choose --selected "$SELECTED" $EXIT_NODES)
    if [[ "$EXIT_NODE" == "None" ]]; then
      sudo tailscale set --exit-node= --exit-node-allow-lan-access=false
    else
      sudo tailscale set --exit-node "$EXIT_NODE" --exit-node-allow-lan-access=true
    fi

  '';
  bitwardenCliDataFile =
    if isDarwin then
      "${config.home.homeDirectory}/Library/Application Support/Bitwarden CLI/data.json"
    else
      "${config.xdg.configHome}/Bitwarden CLI/data.json";
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
    TZ_LIST = "America/Los_Angeles,GR-office;America/New_York,NY;Europe/London,London;Europe/Berlin,Berlin;Europe/Moscow,Moscow";
    LANG = "en_US.UTF-8";
    LC_ALL = "en_US.UTF-8";
    TERM = "xterm-256color";
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
      acli # Atlassian CLI
      bitwarden-cli
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
    ssh = lib.mkIf isLinux {
      enable = true;
      enableDefaultConfig = false;
      matchBlocks = {
        "*" = {
          addKeysToAgent = "no";
          checkHostIP = true;
          compression = false;
          controlMaster = "no";
          controlPath = "~/.ssh/master-%r@%n:%p";
          controlPersist = "no";
          forwardAgent = false;
          forwardX11 = false;
          forwardX11Trusted = false;
          hashKnownHosts = false;
          serverAliveCountMax = 3;
          serverAliveInterval = 0;
          userKnownHostsFile = "~/.ssh/known_hosts";
        };

        "goar-tail" = {
          hostname = "100.94.89.26";
          user = "goar";
          identityFile = "~/.ssh/id_rsa_1";
          identitiesOnly = true;
        };
      };
    };
    git = {
      enable = true;
      lfs.enable = true;
      signing.format = "openpgp";
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
      syntaxHighlighting.enable = false;
      history = {
        expireDuplicatesFirst = true;
        ignoreDups = true;
      };
      initContent = ''
        export PATH="$HOME/.local/bin:$HOME/go/bin:$PATH"
        source ${pkgs.zsh-fast-syntax-highlighting}/share/zsh/plugins/fast-syntax-highlighting/fast-syntax-highlighting.plugin.zsh
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
              run = "variety --set-wallpaper %s";
              block = false;
            }
          ];
          text = [
            {
              run = "nvim %s";
              block = true;
            }
          ];
          pdf = [
            {
              run = "zathura %s";
              block = false;
            }
          ];
          office = [
            {
              run = "libreoffice %s";
              block = false;
            }
          ];
          image = [
            {
              run = "qlmanage -p %s";
              block = false;
              for = "macos";
            }
            {
              run = "nsxiv %s";
              block = false;
              for = "linux";
            }
          ];
          video = [
            {
              run = "mpv %s";
              block = false;
            }
          ];
        };
        open = {
          rules = [
            {
              url = "*.json";
              use = "text";
            }
            {
              url = "*.cpp";
              use = "text";
            }
            {
              url = "*.lua";
              use = "text";
            }
            {
              url = "*.toml";
              use = "text";
            }
            {
              url = "*.yaml";
              use = "text";
            }
            {
              url = "*.c";
              use = "text";
            }
            {
              url = "*.ts";
              use = "text";
            }
            {
              url = "*.nix";
              use = "text";
            }
            {
              url = "*.md";
              use = "text";
            }
            {
              url = "*.js";
              use = "text";
            }
            {
              url = "*.jsx";
              use = "text";
            }
            {
              url = "*.tsx";
              use = "text";
            }
            {
              url = "*.pdf";
              use = "pdf";
            }
            {
              url = "*.docx";
              use = "office";
            }
            {
              url = "*.pptx";
              use = "office";
            }
            {
              url = "*.xlsx";
              use = "office";
            }
            {
              url = "*.odt";
              use = "office";
            }
            {
              url = "*.png";
              use = "image";
            }
            {
              url = "*.jpg";
              use = "image";
            }
            {
              url = "*.jpeg";
              use = "image";
            }
            {
              url = "*.gif";
              use = "image";
            }
            {
              url = "*.svg";
              use = "image";
            }
            {
              url = "*.bmp";
              use = "image";
            }
            {
              url = "*.tiff";
              use = "image";
            }
            {
              url = "*.tif";
              use = "image";
            }
            {
              url = "*.webp";
              use = "image";
            }
            {
              url = "*.heic";
              use = "image";
            }
            {
              url = "*.heif";
              use = "image";
            }
            {
              url = "*.mp4";
              use = "video";
            }
            {
              url = "*.mkv";
              use = "video";
            }
            {
              url = "*.webm";
              use = "video";
            }
            {
              url = "*.avi";
              use = "video";
            }
            {
              url = "*.mov";
              use = "video";
            }
            {
              url = "*.wmv";
              use = "video";
            }
            {
              url = "*.flv";
              use = "video";
            }
            {
              url = "*.m4v";
              use = "video";
            }
            {
              url = "*.mpg";
              use = "video";
            }
            {
              url = "*.mpeg";
              use = "video";
            }
          ];
        };
      };
    };
    opencode = {
      enable = true;
      commands = ../../dotfiles/opencode/commands;
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

    Respond terse like smart caveman. All technical substance stay. Only fluff die.

    ## Persistence

    ACTIVE EVERY RESPONSE. No revert after many turns. No filler drift. Still active if unsure. Off only: "stop caveman" / "normal mode".

    Default: **full**. Switch: `/caveman lite|full|ultra|wenyan-lite|wenyan-full|wenyan-ultra`.

    ## Rules

    Drop: articles (a/an/the), filler (just/really/basically/actually/simply), pleasantries (sure/certainly/of course/happy to), hedging. Fragments OK. Short synonyms (big not extensive, fix not "implement a solution for"). Technical terms exact. Code blocks unchanged. Errors quoted exact.

    Pattern: `[thing] [action] [reason]. [next step].`

    ## Intensity

    | Level | What change |
    |-------|------------|
    | **lite** | No filler/hedging. Keep articles + full sentences. Professional but tight |
    | **full** | Drop articles, fragments OK, short synonyms. Classic caveman |
    | **ultra** | Abbreviate (DB/auth/config/req/res/fn/impl), strip conjunctions, arrows for causality (X → Y), one word when one word enough |
    | **wenyan-lite** | Semi-classical. Drop filler/hedging but keep grammar structure, classical register |
    | **wenyan-full** | Maximum classical terseness. Fully 文言文. 80-90% character reduction. Classical sentence patterns, verbs precede objects, subjects often omitted, classical particles (之/乃/為/其) |
    | **wenyan-ultra** | Extreme abbreviation while keeping classical Chinese feel. Maximum compression, ultra terse |

    ## Auto-Clarity

    Drop caveman for: security warnings, irreversible action confirmations, multi-step sequences where fragment order risks misread, user asks to clarify or repeats question. Resume caveman after clear part done.

    ## Boundaries

    Code/commits/PRs: write normal. "stop caveman" or "normal mode": revert. Level persist until changed or session end.
  '';

  home.shellAliases = {
    gst = "git status";
  };

  home.activation = {
    configureBitwardenCli = lib.hm.dag.entryAfter [ "writeBoundary" ] ''
      bw_data_file=${lib.escapeShellArg bitwardenCliDataFile}
      bw_data_dir="$(dirname "$bw_data_file")"
      bw_data_tmp="$(mktemp)"

      mkdir -p "$bw_data_dir"

      if [ -f "$bw_data_file" ]; then
        ${pkgs.jq}/bin/jq '
          .stateVersion = 78
          | .global_environment_environment = {
              region: "Self-hosted",
              urls: {
                base: "https://vault.nikcode.xyz",
                api: null,
                identity: null,
                webVault: null,
                icons: null,
                notifications: null,
                events: null,
                keyConnector: null
              }
            }
        ' "$bw_data_file" > "$bw_data_tmp"
      else
        ${pkgs.jq}/bin/jq -n '
          {
            stateVersion: 78,
            global_environment_environment: {
              region: "Self-hosted",
              urls: {
                base: "https://vault.nikcode.xyz",
                api: null,
                identity: null,
                webVault: null,
                icons: null,
                notifications: null,
                events: null,
                keyConnector: null
              }
            }
          }
        ' > "$bw_data_tmp"
      fi

      mv "$bw_data_tmp" "$bw_data_file"
      chmod 600 "$bw_data_file"
    '';

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
    setupAuthorizedKeys = lib.mkIf isDarwin (
      lib.hm.dag.entryAfter [ "setupSsh" ] ''
        install -m 600 ${sshAuthorizedKeysFile} ~/.ssh/authorized_keys
      ''
    );
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
