{
  pkgs,
  ...
}:
let
  # Define the script to toggle floating mode for the entire workspace
  toggleFloatWorkspaceScript = pkgs.writeShellApplication {
    name = "toggle-float-workspace";
    # List packages needed by the script at runtime
    runtimeInputs = with pkgs; [
      bash
      jq
      hyprland
    ];
    text = ''
      #!${pkgs.bash}/bin/bash
      # Dependencies (jq, hyprctl) are made available via runtimeInputs

      # Get current workspace ID
      # $() is usually fine, Nix doesn't typically try to interpret it
      ws_id=$(hyprctl activeworkspace -j | jq '.id')
      # Escape shell variables used in the script logic with $
      if [ -z "$ws_id" ] || [ "$ws_id" == "null" ]; then
          echo "Error: Could not determine active workspace ID." >&2
          exit 1
      fi

      # Define a state file path in /tmp
      # ''${ws_id} correctly uses the Nix variable `ws_id` from the outer scope
      # $state_file uses the shell variable defined below
      state_file="/tmp/hypr_float_ws_''${ws_id}.state"

      if [ -f "$state_file" ]; then
        # === Switch back to TILING ===
        # Escape shell variable $ws_id used in echo
        echo "Workspace $ws_id: Switching to tiling mode."
        # Use Nix variable ws_id in the keyword command
        hyprctl keyword workspace "''${ws_id},defaultFloat:false" > /dev/null

        # Pass the *value* of the shell variable $ws_id to jq's variable WSID.
        # The $WSID inside the jq script '. ... $WSID ...' is interpreted by jq itself.
        hyprctl clients -j | jq -r --argjson WSID "$ws_id" \
          '.[] | select(.workspace.id == $WSID and .floating == true) | .address' |
        while read -r addr; do
          # Escape shell variable $addr used in bash regex and hyprctl command
          if [[ "$addr" =~ ^0x[a-fA-F0-9]+$ ]]; then
            hyprctl dispatch togglefloating address:"$addr" > /dev/null
          fi
        done

        # Escape shell variable $state_file used with rm
        rm "$state_file"
      else
        # === Switch to FLOATING ===
        # Escape shell variable $ws_id used in echo
        echo "Workspace $ws_id: Switching to floating mode."
        # Use Nix variable ws_id in the keyword command
        hyprctl keyword workspace "''${ws_id},defaultFloat:true" > /dev/null

        # Pass the *value* of the shell variable $ws_id to jq's variable WSID
        hyprctl clients -j | jq -r --argjson WSID "$ws_id" \
          '.[] | select(.workspace.id == $WSID and .floating == false) | .address' |
        while read -r addr; do
          # Escape shell variable $addr used in bash regex and hyprctl command
           if [[ "$addr" =~ ^0x[a-fA-F0-9]+$ ]]; then
            hyprctl dispatch togglefloating address:"$addr" > /dev/null
           fi
        done

        # Escape shell variable $state_file used with touch
        touch "$state_file"
      fi
    '';
  };
in
{
  imports = [
    ./kbd-backlight.nix
  ];
  home.packages = with pkgs; [
    adwaita-icon-theme
    rofi-wayland
    grimblast # screenshot utility based on grim
    xdg-utils # for opening default programs when clicking links
    glfw-wayland
    pavucontrol # volume control
    swaybg # to set wallpaper
  ];
  wayland.windowManager.hyprland.enable = true;
  wayland.windowManager.hyprland.settings = {
    exec-once = [
      "mako"
      "variety"
      # Clean up any stale state files on login/reload
      "find /tmp -name 'hypr_float_ws_*.state' -delete"
    ];
    exec = [
      "systemctl --user restart waybar"
      "systemctl --user restart network-manager-applet"
    ];
    "$mod" = "SUPER";
    general = {
      gaps_out = 0;
      layout = "master"; # Explicitly set default layout
    };
    env = [
      "XCURSOR_SIZE,24"
    ];
    input = {
      kb_layout = "us,ru";
      kb_options = "grp:win_space_toggle";
      repeat_rate = 30;
      repeat_delay = 250;

      follow_mouse = 1;
      scroll_factor = 0.5;

      touchpad = {
        natural_scroll = "yes";
        scroll_factor = 0.2;
      };

      sensitivity = 0;
    };
    # Styling for window groupbar (window grouping tabs)
    group = {
      groupbar = {
        # font size and weight for window titles
        font_size = 14;
        font_weight_active = "bold";
        font_weight_inactive = "normal";
        # colors from catppuccin palete
        "col.active" = "rgb(89b4fa) rgb(89b4fa)";
        "col.inactive" = "rgb(6c7086) rgb(6c7086)"; # Surface1
        "col.locked_active" = "rgb(89b4fa) rgb(89b4fa)";
        "col.locked_inactive" = "rgb(6c7086) rgb(6c7086)"; # Surface1
        "text_color" = "rgb(1e1e2e)"; # Text

        # sizing - to make text appear on groupbar "gradients" instead of transparent bars.
        # about half the indicator height
        height = 1;
        text_offset = -9;
        # Make the indicator tall enough to render text inside
        indicator_height = 18;

      };
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

    };
    monitor = [
      "desc:Huawei Technologies Co. Inc. MateView,3840x2560@60.000Hz,auto,2.0"
    ];
    workspace = [
      # Ensure no conflicting defaultFloat rules here unless intended statically
      "1, monitor:eDP-1, persistent:true"
      "2, monitor:eDP-1, persistent:true"
      "3, monitor:eDP-1, persistent:true"
      "4, monitor:eDP-1, persistent:true"
      "5, monitor:eDP-1, persistent:true"
      "10, monitor:eDP-1, persistent:true"
    ];
    windowrulev2 = [
      "float, class:^(1Password)$"
      "stayfocused,title:^(Quick Access — 1Password)$"
      "dimaround,title:^(Quick Access — 1Password)$"
      "noanim,title:^(Quick Access — 1Password)$"

      "float, class:^(org.gnome.*)$"
      "float, class:^(pavucontrol|com.saivert.pwvucontrol)$"
      # make pop-up file dialogs floating, centred, and pinned
      "float, title:(Open|Progress|Save File)"
      "center, title:(Open|Progress|Save File)"
      "pin, title:(Open|Progress|Save File)"
      "float, class:^(code)$, initialTitle:^(Visual Studio Code)$"
      "center, class:^(code)$, initialTitle:^(Visual Studio Code)$"
      "pin, class:^(code)$, initialTitle:^(Visual Studio Code)$"

      # throw sharing indicators away
      "workspace special silent, title:^(Firefox — Sharing Indicator)$"
      "workspace special silent, title:^(.*is sharing (your screen|a window)\.)$"
    ];
    bindm = [
      "$mod, mouse:272, movewindow"
      "$mod, mouse:273, resizewindow"
    ];
    bind =
      [
        "$mod+SHIFT, E, exit"
        "$mod, W, killactive"
        "$mod, F, togglefloating"
        "$mod SHIFT, F, exec, ${toggleFloatWorkspaceScript}/bin/toggle-float-workspace"
        "$mod, B, exec, chromium-browser"
        "$mod, Return, exec, alacritty"
        "$mod, D, exec, rofi -show run"
        "$mod, H, movefocus, l"
        "$mod, J, movefocus, d"
        "$mod, K, movefocus, u"
        "$mod, L, movefocus, r"
        "$mod+CTRL, H, resizeactive, -10 0"
        "$mod+CTRL, J, resizeactive, 0 -10"
        "$mod+CTRL, K, resizeactive, 0 10"
        "$mod+CTRL, L, resizeactive, 10 0"
        "$mod, G, togglegroup"
        "$mod, T, lockactivegroup, toggle"
        "$mod+SHIFT, J, changegroupactive, f"
        "$mod+SHIFT, K, changegroupactive, b"
        "$mod+SHIFT, S, exec, grimblast copy area"
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
        "ALT, space, exec, kbd-backlight toggle"
      ]
      ++ (
        # workspaces
        # binds $mod + [shift +] {1..10} to [move to] workspace {1..10}
        builtins.concatLists (
          builtins.genList (
            x:
            let
              ws =
                let
                  c = (x + 1) / 10;
                in
                builtins.toString (x + 1 - (c * 10));
            in
            [
              "$mod, ${ws}, workspace, ${toString (x + 1)}"
              "$mod SHIFT, ${ws}, movetoworkspace, ${toString (x + 1)}"
            ]
          ) 10
        )
      );
  };

  programs = {
    waybar = {
      settings = {
        mainBar = {
          modules-left = [
            "hyprland/workspaces"
          ];
          modules-right = [ "hyprland/language" ];

          "hyprland/workspaces" = {
          };
          "hyprland/language" = {
            "format" = " {}";
            "format-en" = "en";
            "format-ru" = "ру";
          };
        };
      };
    };
  };
  programs.hyprlock = {
    enable = true;
    settings = {
      general = {
        grace = 5;
        hide_cursor = false;
      };
      background = {
        color = "rgba(25, 20, 50, 1.0)";
      };
    };
  };

  home.sessionVariables = {
    NIXOS_OZONE_WL = "1"; # For Electron/Chromium Wayland support
    WLR_NO_HARDWARE_CURSORS = "1"; # Optional: Fix cursor issues on some hardware
    _JAVA_AWT_WM_NONREPARENTING = "1"; # For Java Swing apps
    CLUTTER_BACKEND = "wayland";
    GDK_BACKEND = "wayland"; # Already often default, keep if needed
    MOZ_ENABLE_WAYLAND = "1"; # Firefox Wayland
    QT_QPA_PLATFORM = "wayland;xcb"; # Prefer Wayland for Qt, fallback to X11
    QT_WAYLAND_DISABLE_WINDOWDECORATION = "1"; # Use server-side decorations for Qt
    SDL_VIDEODRIVER = "wayland"; # SDL2 Wayland
    XDG_SESSION_TYPE = "wayland"; # Usually set by display manager/login
    ELECTRON_OZONE_PLATFORM_HINT = "auto"; # Let Electron auto-detect Wayland
  };

  # Services
  services.network-manager-applet.enable = true;
  services.hypridle = {
    enable = true;
    settings = {
      general = {
        # before_sleep_cmd = "loginctl lock-session"; # Example: lock before sleep
        after_sleep_cmd = "hyprctl dispatch dpms on"; # Wake up monitors after sleep
        ignore_dbus_inhibit = false; # Respect apps requestion inhibition (e.g. video players)
        lock_cmd = "pidof hyprlock || hyprlock"; # Lock command, ensure only one instance runs
      };

      listener = [
        {
          timeout = 900; # 15 minutes
          on-timeout = "pidof hyprlock || hyprlock"; # Lock screen
          # on-resume = "notify-send 'Welcome back!'"; # Example resume action
        }
        {
          timeout = 1200; # 20 minutes
          on-timeout = "hyprctl dispatch dpms off"; # Turn off displays
          on-resume = "hyprctl dispatch dpms on"; # Turn displays back on
        }
      ];
    };
  };

  # Electron Flags File
  home.file.".config/electron-flags.conf".text = ''
    --enable-features=WaylandWindowDecorations
    --ozone-platform-hint=auto
  '';
}
