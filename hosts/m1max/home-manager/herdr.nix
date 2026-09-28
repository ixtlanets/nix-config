# Managed Herdr config for darwin hosts (m1max, m3max).
# Derives from the omarchy managed config (dotfiles/omarchy/herdr/config.toml),
# replacing the Linux zsh path with the macOS one.
{ ... }:
let
  linuxConfig = builtins.readFile ../../../dotfiles/omarchy/herdr/config.toml;
  darwinConfig =
    builtins.replaceStrings
      [ "/usr/bin/zsh" ]
      [ "/bin/zsh" ]
      linuxConfig;
in
{
  home.file.".config/herdr/config.toml".text = darwinConfig;
}
