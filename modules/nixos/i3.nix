{
  config,
  pkgs,
  ...
}:
{
  services.displayManager = {
    sddm.enable = true;
    defaultSession = "none+i3";
  };
  services.xserver = {
    enable = true;
    windowManager.i3.enable = true;
  };
}
