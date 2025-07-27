{ pkgs, ... }:
let
  fixText = pkgs.writeShellApplication {
    name = "fix-text";
    runtimeInputs = with pkgs; [
      ollama
      curl
      jq
      wl-clipboard
      xclip
      xsel
      libnotify
    ];
    text = ''
      #!/usr/bin/env bash
      set -eo pipefail

      notify() {
        local title="$1"
        shift
        local body="$1"
        shift || true
        local rid=91142 # replace id to avoid stacking
        if command -v dunstify >/dev/null 2>&1; then
          dunstify -a fix-text -r "$rid" -u low -i edit-paste "$title" "$body"
        elif command -v notify-send >/dev/null 2>&1; then
          notify-send -a fix-text -u low -i edit-paste "$title" "$body"
        else
          printf '[fix-text] %s: %s\n' "$title" "$body" >&2
        fi
      }

      # Clipboard detection (unchanged)
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
      prompt=$'You are a professional copy editor. When given a passage of text, you will:\n1. Correct grammar, spelling, punctuation, and style.\n2. Preserve the author’s original tone, voice, and meaning.\n3. Output only the revised text—no explanations, comments, or formatting notes.'

      # Determine whether to use a remote service or local CLI
      # Preferred: OLLAMA_SERVICE_URL (e.g., http://localhost:11434)

      MODEL="''${OLLAMA_MODEL:-gemma3n}"

      if [[ -n "''${OLLAMA_SERVICE_URL:-}" ]]; then
        # Use HTTP API: /api/generate (non-streaming)
        # Combine system-like instruction with clipboard text, JSON-escape safely via jq
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
          notify "Fix failed" "Smething went wrong"
          exit 1
        fi
      else
        # Fallback to local CLI
        if {
          printf '%s\n' "$prompt"
          "''${PASTE_CMD[@]}"
        } |
          ollama run "$MODEL" |
          "''${COPY_CMD[@]}"; then
          notify "Text fixed" "Copied to clipboard (model: $MODEL)"
        else
          notify "Fix failed" "Smething went wrong"
          exit 1
        fi
      fi
    '';
  };
in
{
  home.packages = [ fixText ];
}
