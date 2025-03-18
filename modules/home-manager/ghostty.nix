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
      font-family = "Hack Nerd Font";
      font-size = 16;
    };
  };
}
