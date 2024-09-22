{ inputs, outputs, lib, config, pkgs, ... }:
{

  home.packages = with pkgs; [
    kanshi
  ];
  systemd.user.services.kanshi = {
    serviceConfig = {
      StartLimitBurst = 5;
      StartLimitIntervalSec = 30;
    };
  };
  services.kanshi = {
    enable = true;
  };
}
