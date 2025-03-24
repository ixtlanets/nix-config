{ pkgs, ... }:
{
  home.file = {
    ".config/awesome" = {
      recursive = true;
      source = "";
    };
  };
}
