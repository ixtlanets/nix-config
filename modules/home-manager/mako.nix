{
  inputs,
  outputs,
  lib,
  config,
  pkgs,
  ...
}:
{
  home.packages = with pkgs; [
    mako
  ];

  services.mako = {
    enable = true;
    borderRadius = 5;
    defaultTimeout = 3000;
    extraConfig = ''
      background-color=#24273a
      text-color=#cad3f5
      border-color=#8aadf4
      progress-color=over #363a4f

      [urgency=high]
      border-color=#f5a97f
    '';
  };
}
