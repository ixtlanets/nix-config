{ inputs, outputs, lib, config, pkgs, ... }: 
{
  services.syncthing.enable = true;
  # Nicely reload system units when changing configs
  systemd.user.startServices = "sd-switch";
}
