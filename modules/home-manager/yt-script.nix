{ pkgs, ... }:
let
  lib = pkgs.lib;
  stdenv = pkgs.stdenv;

  yt-script = pkgs.writeShellApplication {
    name = "yt";
    runtimeInputs =
      (with pkgs; [
        yt-dlp
        coreutils
      ])
      ++ lib.optionals stdenv.isLinux (
        with pkgs;
        [
          wl-clipboard
          xclip
          xsel
        ]
      );

    text = ''
      #!/usr/bin/env bash
      set -eo pipefail

      # Detect clipboard tool
      if [[ "''${OSTYPE:-}" == darwin* ]] && command -v pbpaste >/dev/null 2>&1; then
        PASTE_CMD=(pbpaste)
        COPY_CMD=(pbcopy)
      elif [[ -n "''${WAYLAND_DISPLAY-}" ]] && command -v wl-paste >/dev/null 2>&1; then
        PASTE_CMD=(wl-paste)
        COPY_CMD=(wl-copy)
      elif command -v xclip >/dev/null 2>&1; then
        PASTE_CMD=(xclip -selection clipboard -o)
        COPY_CMD=(xclip -selection clipboard -i)
      elif command -v xsel >/dev/null 2>&1; then
        PASTE_CMD=(xsel --clipboard --output)
        COPY_CMD=(xsel --clipboard --input)
      else
        echo "yt: no clipboard tool found" >&2
        exit 1
      fi

      # Get URL from clipboard
      URL=$("''${PASTE_CMD[@]}")

      # Basic URL validation
      if [[ ! "$URL" =~ ^https?:// ]]; then
        echo "yt: clipboard does not contain a valid URL: $URL" >&2
        exit 1
      fi

      # Ensure output directory exists
      mkdir -p ~/Videos

      # Clear clipboard
      printf "" | "''${COPY_CMD[@]}"

      # Start download
      yt-dlp \
        --config-location "''${XDG_CONFIG_HOME:-$HOME/.config}/yt-dlp/config" \
        --output "$HOME/Videos/%(title)s.%(ext)s" \
        "$URL"
    '';
  };
in
{
  home.packages = [ yt-script ];
}
