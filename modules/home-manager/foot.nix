
{ inputs, outputs, lib, config, pkgs, ... }:
{
  programs = {
    foot = {
      enable = true;
    };
  };
home.file.".config/foot/foot.ini".text = builtins.readFile ../../dotfiles/foot.ini;
}
