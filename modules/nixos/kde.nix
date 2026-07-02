{ pkgs, ... }:
{
  services.xserver.enable = true;
  services.displayManager.sddm.enable = true;
  services.displayManager.sddm.wayland.enable = true;
  services.desktopManager.plasma6.enable = true;

  xdg.portal = {
    enable = true;
    config.common.default = [ "kde" ];
    extraPortals = with pkgs.kdePackages; [ xdg-desktop-portal-kde ];
  };

  environment.systemPackages = with pkgs.kdePackages; [
    dolphin
    kio-extras
  ];
}
