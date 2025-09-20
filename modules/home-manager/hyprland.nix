{
  pkgs,
  ...
}:
let
  handle_monitor_connect = pkgs.writeShellScriptBin "handle_monitor_connect" ''
    set -euo pipefail

    ${pkgs.variety}/bin/variety --next

    handle() {
      case "$1" in
        monitoradded*)
          hyprctl dispatch moveworkspacetomonitor "1 1"
          hyprctl dispatch moveworkspacetomonitor "2 1"
          hyprctl dispatch moveworkspacetomonitor "3 1"
          hyprctl dispatch moveworkspacetomonitor "4 1"
          hyprctl dispatch moveworkspacetomonitor "5 1"
          ;;
      esac
    }

    ${pkgs.socat}/bin/socat - "UNIX-CONNECT:$XDG_RUNTIME_DIR/hypr/$HYPRLAND_INSTANCE_SIGNATURE/.socket2.sock" \
      | while read -r line; do handle "$line"; done
  '';
  take-screenshot = pkgs.writeShellScriptBin "take-screenshot" ''
    OUTPUT_DIR="$HOME/Pictures"

    if [[ ! -d "$OUTPUT_DIR" ]]; then
      notify-send "Screenshot directory does not exist: $OUTPUT_DIR" -u critical -t 3000
      exit 1
    fi

    pkill slurp || hyprshot -m region --raw |
      satty --filename - \
        --output-filename "$OUTPUT_DIR/screenshot-$(date +'%Y-%m-%d_%H-%M-%S').png" \
        --early-exit \
        --actions-on-enter save-to-clipboard \
        --save-after-copy \
        --copy-command 'wl-copy'
  '';
in
{
  imports = [
    ./kbd-backlight.nix
    ./walker.nix
  ];
  home.packages = with pkgs; [
    socat
    adwaita-icon-theme
    adwaita-qt
    grimblast # screenshot utility based on grim
    slurp # Select a region in a Wayland compositor
    hyprshot # take screenshots in Hyprland using your mouse
    xdg-utils # for opening default programs when clicking links
    glfw-wayland
    pavucontrol # volume control
    swaybg # to set wallpaper
    clipse # clipboard manager
    wiremix # TUI for audio
    satty # Screenshot annotaion
    handle_monitor_connect
    take-screenshot
    hyprpolkitagent
  ];
  wayland.windowManager.hyprland.enable = true;
  wayland.windowManager.hyprland.settings = {
    exec-once = [
      "mako"
      "variety"
      "clipse -listen" # start clipboard manager
      "walker"
      # Clean up any stale state files on login/reload
      "find /tmp -name 'hypr_float_ws_*.state' -delete"
      "handle_monitor_connect"
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
      "GTK_APPLICATION_PREFER_DARK_THEME,1"
      "GTK_THEME,Adwaita:dark"
      "GTK_THEME_VARIANT,dark"
      "XCURSOR_SIZE,24"
    ];
    input = {
      kb_layout = "us,ru";
      kb_options = "grp:win_space_toggle";
      repeat_rate = 30;
      repeat_delay = 250;

      follow_mouse = 1;
      # scroll_factor = 0.5;

      touchpad = {
        natural_scroll = "yes";
        scroll_factor = 0.5;
      };

      # sensitivity = 0;
    };
    # Styling for window groupbar (window grouping tabs)
    group = {
      groupbar = {
        # font size and weight for window titles
        font_size = 14;
        font_weight_active = "bold";
        font_weight_inactive = "normal";
        # colors from catppuccin palete
        "col.active" = "rgb(7f849c) rgb(9399b2)";
        "col.inactive" = "rgb(313244) rgb(313244)"; # Surface1
        "col.locked_active" = "rgb(313244) rgb(313244)";
        "col.locked_inactive" = "rgb(7f849c) rgb(9399b2)"; # Surface1
        "text_color" = "rgb(cdd6f4)"; # Text

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
    misc = {
      anr_missed_pings = 5;
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

      shadow = {
        enabled = true;
        range = 10;
        render_power = 10;
        color = "rgba(1a1a1aee)";
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
      "float, class:(Wiremix|org.gnome.NautilusPreviewer|com.gabm.satty|TUI.float)"
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
      # clipse - clipboard manager
      "float, class:^(clipse)$"
      "size 622 652,class:^(clipse)$"
    ];
    bindm = [
      "$mod, mouse:272, movewindow"
      "$mod, mouse:273, resizewindow"
    ];
    # binds which works even on lock screen
    bindl = [
      ",XF86MonBrightnessUp, exec, swayosd-client --brightness raise"
      ",XF86MonBrightnessDown, exec, swayosd-client --brightness lower"
      "ALT, space, exec, kbd-backlight toggle"
    ];
    bind = [
      "$mod+SHIFT, E, exit"
      "$mod, W, killactive"
      "$mod, F, togglefloating"
      "$mod, B, exec, chromium-browser"
      "$mod, Return, exec, ghostty"
      "$mod, D, exec, walker -p 'start'"
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
      "$mod+SHIFT, S, exec, take-screenshot"
      "$mod+SHIFT, T, exec, fix-text"
      ",XF86AudioRaiseVolume, exec, swayosd-client --output-volume raise"
      ",XF86AudioLowerVolume, exec, swayosd-client --output-volume lower"
      ",XF86AudioMute, exec, swayosd-client --output-volume mute-toggle"
      ",XF86AudioMicMute, exec, swayosd-client --input-volume mute-toggle"
      "$mod, V, exec, ghostty --class clipse -e 'clipse'"
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
  services.hyprpolkitagent.enable = true; # Hyprland polkit agent
  services.gnome-keyring.enable = true;
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
  services.swayosd = {
    enable = true;
    stylePath = pkgs.writeText "style.css" ''
      @define-color background-color #1a1b26;
      @define-color border-color #33ccff;
      @define-color label #a9b1d6;
      @define-color image #a9b1d6;
      @define-color progress #a9b1d6;

      window {
        border-radius: 40px;
        opacity: 0.97;
        border: 2px solid @border-color;

        background-color: @background-color;
      }

      label {
        font-family: 'Hack Nerd Font';
        font-size: 11pt;

        color: @label;
      }

      image {
        color: @image;
      }

      progressbar {
        border-radius: 40px;
      }

      progress {
        background-color: @progress;
      }
    '';
  };

  # Electron Flags File
  home.file.".config/electron-flags.conf".text = ''
    --enable-features=WaylandWindowDecorations
    --ozone-platform-hint=auto
  '';
}
