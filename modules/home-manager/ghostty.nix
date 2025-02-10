{
  inputs,
  outputs,
  lib,
  config,
  pkgs,
  ...
}:
{
  home.file.".config/ghostty/config".text = ''
    font-family = "Hack Nerd Font"
    font-size = 16
    theme = catppuccin-mocha
    quit-after-last-window-closed = true
    macos-non-native-fullscreen = true
    macos-option-as-alt = true
  '';
}
