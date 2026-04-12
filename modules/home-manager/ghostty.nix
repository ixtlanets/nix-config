{
  inputs,
  outputs,
  lib,
  config,
  pkgs,
  ...
}:
{
  programs.ghostty = {
    enable = true;
    settings = {
      theme = "catppuccin-mocha";
      font-family = "Hack Nerd Font Mono";
      font-size = 16;
    };
  };
}
