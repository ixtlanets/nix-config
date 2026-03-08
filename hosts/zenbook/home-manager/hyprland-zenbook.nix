{ ... }:
{
  home.sessionVariables = {
    HYPR_INTERNAL_MONITOR = "eDP-1";
    HYPR_INTERNAL_MONITOR_SCALE = "2.0";
  };

  wayland.windowManager.hyprland.settings = {
    monitor = [
      "eDP-1,preferred,auto,2.0"
    ];
  };
}
