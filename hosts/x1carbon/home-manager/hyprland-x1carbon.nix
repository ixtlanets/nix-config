{ lib, ... }:
{
  home.sessionVariables = {
    HYPR_INTERNAL_MONITOR = "eDP-1";
    HYPR_INTERNAL_MONITOR_POLICY = "external-only";
    HYPR_INTERNAL_MONITOR_SCALE = "1.5";
  };

  wayland.windowManager.hyprland.settings = {
    decoration = {
      blur.enabled = lib.mkForce false;
      shadow.enabled = lib.mkForce false;
    };
  };
}
