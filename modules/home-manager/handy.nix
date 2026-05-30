{ lib, pkgs, ... }:
let
  voiceTyping = import ./voice-typing-words.nix { inherit lib; };
  handyCustomWordsJson = pkgs.writeText "handy-custom-words.json" (
    builtins.toJSON voiceTyping.handyCustomWords
  );
in
{
  config = lib.mkIf pkgs.stdenv.isDarwin {
    home.activation.updateHandyCustomWords = lib.hm.dag.entryAfter [ "writeBoundary" ] ''
      app_dir="$HOME/Library/Application Support/com.pais.handy"
      settings_file="$app_dir/settings_store.json"

      /bin/mkdir -p "$app_dir"

      input_file="$settings_file"
      cleanup_input=false
      if [ ! -f "$settings_file" ]; then
        input_file="$(/usr/bin/mktemp "$app_dir/settings_store.input.XXXXXX")"
        /usr/bin/printf '%s\n' '{"settings":{}}' > "$input_file"
        cleanup_input=true
      fi

      tmp_file="$(/usr/bin/mktemp "$app_dir/settings_store.json.XXXXXX")"
      if ${pkgs.jq}/bin/jq --slurpfile customWords ${handyCustomWordsJson} \
        '.settings = (.settings // {}) | .settings.custom_words = $customWords[0]' \
        "$input_file" > "$tmp_file"; then
        /bin/mv "$tmp_file" "$settings_file"
        echo "Updated Handy custom words in $settings_file"
      else
        echo "Skipping Handy custom words update: $settings_file is not valid JSON"
        /bin/rm -f "$tmp_file"
      fi

      if [ "$cleanup_input" = true ]; then
        /bin/rm -f "$input_file"
      fi
    '';
  };
}
