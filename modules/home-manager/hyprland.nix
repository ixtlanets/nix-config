{ inputs, outputs, lib, config, pkgs, ... }:
{
  home.packages = with pkgs; [
    gnome.adwaita-icon-theme
    rofi-wayland
    grim # screenshot functionality
    slurp # screenshot functionality
    xdg-utils # for opening default programs when clicking links
    glfw-wayland
    polkit-kde-agent
  ];
  wayland.windowManager.hyprland.enable = true;
  wayland.windowManager.hyprland.settings = {
    exec-once = [ "mako"
      "waybar"
      "variety" ];
    "$mod" = "SUPER";
    input = {
      kb_layout = "us,ru";
      kb_options = "grp:win_space_toggle";

      follow_mouse = 1;

      touchpad = {
        natural_scroll = "yes";
      };

      sensitivity = 0;
    };
    decoration = {
      rounding = 2;
      blur = {
        enabled = "yes";
        size = 3;
        passes = 1;
        new_optimizations = "on";
      };

      drop_shadow = "yes";
      shadow_range = 4;
      shadow_render_power = 3;
      "col.shadow" = "rgba(1a1a1aee)";
    };
    bind =
      [
      "$mod+SHIFT, E, exit"
        "$mod, W, killactive"
        "$mod, F, togglefloating"
        "$mod, B, exec, chromium-browser"
        "$mod, Return, exec, foot"
        "$mod, D, exec, rofi -show run"
        "$mod, H, movefocus, l"
        "$mod, J, movefocus, d"
        "$mod, K, movefocus, u"
        "$mod, L, movefocus, r"
      ]
      ++ (
# workspaces
# binds $mod + [shift +] {1..10} to [move to] workspace {1..10}
          builtins.concatLists (builtins.genList (
              x: let
              ws = let
              c = (x + 1) / 10;
              in
              builtins.toString (x + 1 - (c * 10));
              in [
              "$mod, ${ws}, workspace, ${toString (x + 1)}"
              "$mod SHIFT, ${ws}, movetoworkspace, ${toString (x + 1)}"
              ]
              )
            10)
         );
  };

  programs = {
    waybar = {
      settings = {
        mainBar = {
          modules-left = [ "hyprland/workspaces" "hyprland/language" "hyprland/mode" ];

          "hyprland/workspaces" = {
            disable-scroll = true;
            all-outputs = true;
            "persistent_workspaces"= {
              "1"= [];
              "2"= [];
              "3"= [];
              "4"= [];
            };
          };
          "hyprland/language" = {
            "format"= " {}";
            "min-length" = 5;
            "tooltip"= false;
          };
          "hyprland/submap" = {
            "format"= "<span style=\"italic\">{}</span>";
          };
        };
      };
    };

  };

  home.sessionVariables.NIXOS_OZONE_WL = "1";
}

