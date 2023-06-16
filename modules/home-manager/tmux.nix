{ inputs, outputs, lib, config, pkgs, ... }: 
{
  nixpkgs = {
    overlays = [
      (final: prev: {
       tmuxPluginsDracula = final.tmuxPlugins.dracula.overrideAttrs (oldAttrs: {
           version = "2.2.0";
           src = pkgs.fetchFromGitHub {
           owner = "dracula";
           repo = "tmux";
           rev = "v2.2.0";
           sha256 = "9p+KO3/SrASHGtEk8ioW+BnC4cXndYx4FL0T70lKU2w=";
           };
           });
       })
    ];
  };
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
          plugin = pkgs.tmuxPluginsDracula;
          extraConfig = ''
            set -g @dracula-show-fahrenheit false
            set -g @dracula-plugins "battery cpu-usage ram-usage weather time"
            set -g @dracula-show-left-icon session
            set -g @dracula-day-month true
            set -g @dracula-military-time true
            '';
        }
    ];
    extraConfig = ''

      '';
  };
}
