{
  pkgs,
  ...
}:
{
  programs.hyprland = {
    enable = true;
    portalPackage = with pkgs; xdg-desktop-portal-hyprland;
    withUWSM = true;
    xwayland.enable = true;
  };

  programs.hyprlock.enable = true;
}
