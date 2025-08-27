{
  inputs,
  outputs,
  lib,
  config,
  pkgs,
  ...
}:
{
  programs.tmux = {
    enable = true;
    clock24 = true;
    baseIndex = 1;
    keyMode = "vi";
    plugins = [
      pkgs.tmuxPlugins.sensible
      pkgs.tmuxPlugins.pain-control
      pkgs.tmuxPlugins.urlview
      pkgs.tmuxPlugins.prefix-highlight
      {
        plugin = pkgs.tmuxPlugins.dracula;
        extraConfig = ''
          set -g @dracula-show-fahrenheit false
          set -g @dracula-plugins "battery cpu-usage ram-usage time"
          set -g @dracula-show-left-icon session
          set -g @dracula-day-month true
          set -g @dracula-military-time true
          set -g @dracula-battery-label ""

          set -g allow-passthrough on

          set -ga update-environment TERM
          set -ga update-environment TERM_PROGRAM
        '';
      }
    ];
    extraConfig = ''
      # temp fix for https://github.com/tmux-plugins/tmux-sensible/issues/74
      set -g default-shell ${pkgs.zsh}/bin/zsh
      set -g default-command "${pkgs.zsh}/bin/zsh -l"
    '';
  };
}
