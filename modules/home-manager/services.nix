{
  inputs,
  outputs,
  lib,
  config,
  pkgs,
  ...
}:
{
  services.syncthing.enable = true;
  # Nicely reload system units when changing configs
  systemd.user.startServices = "sd-switch";

  systemd.user.services.voxtype = {
    Unit = {
      Description = "Voxtype voice typing daemon";
      After = [ "graphical-session.target" ];
      PartOf = [ "graphical-session.target" ];
    };

    Service = {
      ExecStart = "${pkgs.voxtype-onnx}/bin/voxtype";
      Restart = "on-failure";
      RestartSec = 3;
    };

    Install.WantedBy = [ "graphical-session.target" ];
  };
}
