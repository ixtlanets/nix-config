
{ inputs, outputs, lib, config, pkgs, ... }:
{
  programs = {
    foot = {
      enable = true;
      catppuccin.enable = true;
      settings = {
        main = {
          font = "Hack Nerd Font:size=16";
          dpi-aware = "yes";
          term = "xterm-256color";
        };
      };
    };
  };
}
