{
  config,
  inputs,
  lib,
  pkgs,
  ...
}:
let
  voiceTyping = import ./voice-typing-words.nix { inherit lib; };
  handyCustomWordsJson = pkgs.writeText "handy-custom-words.json" (
    builtins.toJSON voiceTyping.handyCustomWords
  );
  handyPackage = inputs.handy.packages.${pkgs.stdenv.hostPlatform.system}.handy;
  updateLinuxHandySettings = pkgs.writeShellApplication {
    name = "update-handy-settings";
    runtimeInputs = [
      pkgs.coreutils
      pkgs.jq
    ];
    text = ''
      settings_dir="''${XDG_DATA_HOME:-$HOME/.local/share}/com.pais.handy"
      settings_file="$settings_dir/settings_store.json"
      umask 077
      mkdir -p "$settings_dir"

      input_file="$settings_file"
      cleanup_input=false
      tmp_file=""
      cleanup() {
        if [[ -n "$tmp_file" ]]; then
          rm -f "$tmp_file"
        fi
        if [[ "$cleanup_input" == true ]]; then
          rm -f "$input_file"
        fi
      }
      trap cleanup EXIT

      if [[ ! -f "$settings_file" ]]; then
        input_file="$(mktemp "$settings_dir/settings_store.input.XXXXXX")"
        printf '%s\n' '{"settings":{}}' > "$input_file"
        cleanup_input=true
      fi

      tmp_file="$(mktemp "$settings_dir/settings_store.json.XXXXXX")"
      jq --slurp --slurpfile customWords ${handyCustomWordsJson} \
        -f ${./handy-settings.jq} "$input_file" > "$tmp_file"
      chmod 0600 "$tmp_file"

      if [[ -f "$settings_file" ]] && cmp -s "$settings_file" "$tmp_file"; then
        chmod 0600 "$settings_file"
      else
        mv "$tmp_file" "$settings_file"
      fi
    '';
  };
in
{
  options.voiceTyping.handy.enable = lib.mkOption {
    type = lib.types.bool;
    default = pkgs.stdenv.isDarwin;
    description = "Whether to configure Handy voice typing.";
  };

  config = lib.mkMerge [
    (lib.mkIf pkgs.stdenv.isDarwin {
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
    })
    (lib.mkIf (pkgs.stdenv.isLinux && config.voiceTyping.handy.enable) {
      home.packages = [
        handyPackage
        pkgs.dotool
        pkgs.which
        pkgs.wl-clipboard
        pkgs.wtype
      ];

      systemd.user.services.handy = {
        Unit = {
          Description = "Handy speech-to-text";
          After = [ "graphical-session.target" ];
          PartOf = [ "graphical-session.target" ];
        };
        Service = {
          ExecStartPre = "${updateLinuxHandySettings}/bin/update-handy-settings";
          ExecStart = "${handyPackage}/bin/handy --start-hidden";
          Environment = "PATH=${
            lib.makeBinPath [
              handyPackage
              pkgs.coreutils
              pkgs.dotool
              pkgs.which
              pkgs.wl-clipboard
              pkgs.wtype
            ]
          }";
          Restart = "on-failure";
          RestartSec = 5;
        };
        Install.WantedBy = [ "graphical-session.target" ];
      };
    })
  ];
}
