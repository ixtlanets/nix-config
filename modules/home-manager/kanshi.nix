{ inputs, outputs, lib, config, pkgs, ... }:
{
  services.kanshi = {
    enable = true;
  };
}
