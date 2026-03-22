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
      ExecStart = "${pkgs.voxtype-vulkan}/bin/voxtype";
      Restart = "on-failure";
      RestartSec = 3;
      Environment = [
        "VOXTYPE_VULKAN_DEVICE=nvidia"
        "VK_ICD_FILENAMES=/run/opengl-driver/share/vulkan/icd.d/nvidia_icd.x86_64.json"
      ];
    };

    Install.WantedBy = [ "graphical-session.target" ];
  };
}
