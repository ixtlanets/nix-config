{ pkgs, ... }:
let
  lib = pkgs.lib;
  stdenv = pkgs.stdenv;

  fixText = pkgs.writeShellApplication {
    name = "fix-text";
    runtimeInputs =
      # Common
      (with pkgs; [
        curl
        jq
      ])
      # Linux-only (clipboard + libnotify)
      ++ lib.optionals stdenv.isLinux (
        with pkgs;
        [
          wl-clipboard
          xclip
          xsel
          libnotify
        ]
      )
      # macOS-only (native notifier)
      ++ lib.optionals stdenv.isDarwin (with pkgs; [ terminal-notifier ]);

    text = ''
      #!/usr/bin/env bash
      set -eo pipefail

      notify() {
        local title="$1"
        local body="${"2:-"}"
        local rid=91142 # replace id to avoid stacking

        # macOS: use native notifications first, avoid notify-send/libnotify
        if [[ "''${OSTYPE:-}" == darwin* ]]; then
          if command -v terminal-notifier >/dev/null 2>&1; then
            terminal-notifier -title "fix-text" -subtitle "$title" -message "$body" || true
          elif command -v osascript >/dev/null 2>&1; then
            osascript -e 'on run argv
              display notification (item 1 of argv) with title "fix-text" subtitle (item 2 of argv)
            end run' "$body" "$title" || true
          else
            printf '[fix-text] %s: %s\n' "$title" "$body" >&2
          fi

        # Linux: prefer dunstify, then notify-send
        elif command -v dunstify >/dev/null 2>&1; then
          dunstify -a fix-text -r "$rid" -u low -i edit-paste "$title" "$body" || true
        elif command -v notify-send >/dev/null 2>&1; then
          notify-send -a fix-text -u low -i edit-paste "$title" "$body" || true
        else
          printf '[fix-text] %s: %s\n' "$title" "$body" >&2
        fi
      }

      # Clipboard detection
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
        echo "No supported clipboard tool found." >&2
        exit 1
      fi

      # Editing prompt
      prompt=$'You are a professional copy editor. When given a passage of text, you will:\n1. Correct grammar, spelling, punctuation, and style.\n2. Preserve the author’s original tone, voice, and meaning.\n3. Output only the revised text—no explanations, comments, or formatting notes.\n---\nINPUT:\n'

      MODEL="''${OLLAMA_MODEL:-gemma3n}"

      if [[ -n "''${OLLAMA_SERVICE_URL:-}" ]]; then
        if {
          printf '%s\n' "$prompt"
          "''${PASTE_CMD[@]}"
        } |
          jq -Rs --arg model "$MODEL" '{model:$model, prompt: ., stream:false}' |
          curl -sS -X POST -H 'Content-Type: application/json' \
            "$OLLAMA_SERVICE_URL/api/generate" -d @- |
          jq -r '.response' |
          "''${COPY_CMD[@]}"; then
          notify "Text fixed" "Copied to clipboard (model: $MODEL)"
        else
          notify "Fix failed" "Something went wrong"
          exit 1
        fi
      else
        if {
          printf '%s\n' "$prompt"
          "''${PASTE_CMD[@]}"
        } |
          ollama run "$MODEL" |
          "''${COPY_CMD[@]}"; then
          notify "Text fixed" "Copied to clipboard (model: $MODEL)"
        else
          notify "Fix failed" "Something went wrong"
          exit 1
        fi
      fi
    '';
  };
in
{
  home.packages = [ fixText ];
}
