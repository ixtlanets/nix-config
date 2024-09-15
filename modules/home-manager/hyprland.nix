{ inputs, outputs, lib, config, pkgs, ... }:
{
  home.packages = with pkgs; [
    adwaita-icon-theme
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
      "variety" ];
    "$mod" = "SUPER";
    general = {
      gaps_out = 0;
    };
    input = {
      kb_layout = "us,ru";
      kb_options = "grp:win_space_toggle";
      repeat_rate	= 30;
      repeat_delay = 250;

      follow_mouse = 1;
      scroll_factor= 0.5;

      touchpad = {
        natural_scroll = "yes";
        scroll_factor= 0.2;
      };

      sensitivity = 0;
    };
    xwayland = {
      force_zero_scaling = true;
    };
    animation = [
      "windows, 0, 1, default"
        "border, 1, 3, default"
        "borderangle, 1, 2, default"
        "fade, 1, 2, default"
        "workspaces, 0, 1, default"
    ];
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
    bindm = [
      "$mod, mouse:272, movewindow"
        "$mod, mouse:273, resizewindow"
    ];
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
        "$mod, G, togglegroup"
        "$mod, T, lockactivegroup, toggle"
        "$mod+SHIFT, J, changegroupactive, b"
        "$mod+SHIFT, K, changegroupactive, f"
        "$mod+SHIFT, S, exec, grim -g \"$(slurp -d)\" - | wl-copy"
        ",XF86MonBrightnessUp, exec, light -A 10"
        ",XF86MonBrightnessDown, exec, light -U 10"
        "SHIFT ,XF86MonBrightnessUp, exec, light -A 1"
        "SHIFT ,XF86MonBrightnessDown, exec, light -U 1"
        ",XF86AudioRaiseVolume, exec, wpctl set-volume @DEFAULT_AUDIO_SINK@ 0.1+"
        ",XF86AudioLowerVolume, exec, wpctl set-volume @DEFAULT_AUDIO_SINK@ 0.1-"
        "SHIFT ,XF86AudioRaiseVolume, exec, wpctl set-volume @DEFAULT_AUDIO_SINK@ 0.01+"
        "SHIFT ,XF86AudioLowerVolume, exec, wpctl set-volume @DEFAULT_AUDIO_SINK@ 0.01-"
        ",XF86AudioMute, exec, wpctl set-volume @DEFAULT_AUDIO_SINK@ toggle"
        ",XF86AudioMicMute, exec, wpctl set-mute @DEFAULT_AUDIO_SOURCE@ toggle"
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
          modules-left = [ "hyprland/workspaces" "hyprland/mode" ];
          modules-right = ["hyprland/language"];

          "hyprland/workspaces" = {
            all-outputs = true;
            "persistent-workspaces"= {
              "*"= 5;
            };
          };
          "hyprland/language" = {
            "format"= " {}";
            "format-en" = "en";
            "format-ru" = "ру";
          };
          "hyprland/submap" = {
            "format"= "<span style=\"italic\">{}</span>";
          };
        };
      };
    };

  };

  home.sessionVariables.NIXOS_OZONE_WL = "1";
  home.sessionVariables.WLR_NO_HARDWARE_CURSORS = "1";
  home.sessionVariables.ELECTRON_OZONE_PLATFORM_HINT = "auto";
  services.network-manager-applet.enable = true;
  home.file.".config/electron-flags.conf".text = ''
--enable-features=WaylandWindowDecorations
--ozone-platform-hint=auto
  '';
}

