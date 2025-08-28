{
  pkgs,
  ...
}:
{
  xdg.portal = {
    enable = true;
    config = {
      common = {
        default = [ "hyprland" ];
      };
      hyprland = {
        default = [
          "hyprland"
        ];
      };
    };
    extraPortals = with pkgs; [
      xdg-desktop-portal-hyprland
    ];
    # xdgOpenUsePortal = true; # for some reason now it's not working
  };

  programs.hyprland = {
    enable = true;
    portalPackage = with pkgs; xdg-desktop-portal-hyprland;
    xwayland.enable = true;
  };

  programs.hyprlock.enable = true;
}
