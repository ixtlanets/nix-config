{ pkgs, ... }:
let
  lib = pkgs.lib;
  transcribe-media = pkgs.writeShellApplication {
    name = "transcribe-media";
    runtimeInputs = with pkgs; [
      coreutils
      jq
    ];
    text = builtins.readFile ../../dotfiles/omarchy/bin/transcribe-media;
  };
in
{
  home.packages = lib.optionals pkgs.stdenv.isDarwin [ transcribe-media ];
}
