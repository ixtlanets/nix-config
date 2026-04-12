{
  inputs,
  outputs,
  lib,
  config,
  pkgs,
  ...
}:
{
  programs = {
    foot = {
      enable = true;
      catppuccin.enable = true;
      settings = {
        main = {
          font = "Hack Nerd Font Mono:size=14";
          term = "xterm-256color";
        };
      };
    };
  };
}
