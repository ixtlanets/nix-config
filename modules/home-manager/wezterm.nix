{
  inputs,
  outputs,
  lib,
  config,
  pkgs,
  ...
}:
{
  programs.wezterm = {
    enable = true;
    extraConfig = ''
      return {
        color_scheme = "Catppuccin Mocha",
        font = wezterm.font("Hack Nerd Font"),
        font_size = 16,
        hide_tab_bar_if_only_one_tab = true,
      }
    '';
  };
}