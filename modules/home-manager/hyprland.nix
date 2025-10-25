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
  spotlight-toggle = pkgs.writeShellScriptBin "spotlight-toggle" ''
    SPOTLIGHT_STATE_FILE="/tmp/spotlight_state"
    SPOTLIGHT_OVERLAY_SCRIPT="${pkgs.writeShellScriptBin "spotlight-overlay" ""}/bin/spotlight-overlay"

    # Check if spotlight is already active
    if [ -f "$SPOTLIGHT_STATE_FILE" ]; then
      # Spotlight is active, deactivate it
      rm -f "$SPOTLIGHT_STATE_FILE"
      pkill -f "spotlight-overlay" 2>/dev/null || true
      hyprctl dispatch closewindow "title:spotlight-overlay" 2>/dev/null || true
    else
      # Spotlight is inactive, activate it
      echo "active" > "$SPOTLIGHT_STATE_FILE"
      "$SPOTLIGHT_OVERLAY_SCRIPT" &
    fi
  '';
  spotlight-overlay = pkgs.writeShellScriptBin "spotlight-overlay" ''
    SPOTLIGHT_STATE_FILE="/tmp/spotlight_state"
    OVERLAY_TITLE="spotlight-overlay"
    CIRCLE_RADIUS=48

    # Function to create overlay window
    create_overlay() {
      local monitor_info=$(hyprctl monitors -j | ${pkgs.jq}/bin/jq -r '.[0]')
      local width=$(echo "$monitor_info" | ${pkgs.jq}/bin/jq -r '.width')
      local height=$(echo "$monitor_info" | ${pkgs.jq}/bin/jq -r '.height')
      local x=$(echo "$monitor_info" | ${pkgs.jq}/bin/jq -r '.x')
      local y=$(echo "$monitor_info" | ${pkgs.jq}/bin/jq -r '.y')
      
      # Create a fullscreen overlay window
      hyprctl dispatch exec "[float; size ''${width} ''${height}; pos ''${x} ''${y}; noinitialfocus; nodim; title ''${OVERLAY_TITLE}] ${pkgs.kitty}/bin/kitty --class spotlight-overlay bash -c '
        # Create the overlay effect
        while [ -f "'"$SPOTLIGHT_STATE_FILE"'" ]; do
          # Get current cursor position
          cursor_pos=$(hyprctl cursorpos -j)
          cursor_x=$(echo "$cursor_pos" | ${pkgs.jq}/bin/jq -r ".x")
          cursor_y=$(echo "$cursor_pos" | ${pkgs.jq}/bin/jq -r ".y")
          
          # Clear screen and create dark background with clear circle
          printf "\033[2J\033[H"
          
          # Create dark overlay using terminal background
          printf "\033]11;#000000\007"
          
          # Move cursor to spotlight position and create clear area
          # We use a simple approach: move cursor to the spotlight position
          printf "\033[%d;%dH" $((cursor_y)) $((cursor_x))
          
          sleep 0.016  # ~60 FPS refresh rate
        done
      '"
    }

    # Function to update spotlight position
    update_spotlight() {
      while [ -f "$SPOTLIGHT_STATE_FILE" ]; do
        # Get current cursor position
        cursor_pos=$(hyprctl cursorpos -j 2>/dev/null)
        if [ $? -eq 0 ]; then
          cursor_x=$(echo "$cursor_pos" | ${pkgs.jq}/bin/jq -r ".x" 2>/dev/null)
          cursor_y=$(echo "$cursor_pos" | ${pkgs.jq}/bin/jq -r ".y" 2>/dev/null)
          
          if [ "$cursor_x" != "null" ] && [ "$cursor_y" != "null" ]; then
            # Update overlay window position to follow cursor
            # This is a simplified approach - in practice, we might need a more sophisticated method
            hyprctl dispatch movewindow "exact ''${cursor_x} ''${cursor_y} ''${OVERLAY_TITLE}" 2>/dev/null || true
          fi
        fi
        sleep 0.016  # ~60 FPS refresh rate
      done
    }

    # Main execution
    create_overlay
    sleep 0.5  # Give window time to create
    update_spotlight

    # Clean up when done
    hyprctl dispatch closewindow "title:''${OVERLAY_TITLE}" 2>/dev/null || true
  '';
  spotlight-state = pkgs.writeShellScriptBin "spotlight-state" ''
    SPOTLIGHT_STATE_FILE="/tmp/spotlight_state"

    case "$1" in
      "active")
        if [ -f "$SPOTLIGHT_STATE_FILE" ]; then
          echo "true"
        else
          echo "false"
        fi
        ;;
      "activate")
        echo "active" > "$SPOTLIGHT_STATE_FILE"
        ;;
      "deactivate")
        rm -f "$SPOTLIGHT_STATE_FILE"
        ;;
      "toggle")
        if [ -f "$SPOTLIGHT_STATE_FILE" ]; then
          rm -f "$SPOTLIGHT_STATE_FILE"
          echo "deactivated"
        else
          echo "active" > "$SPOTLIGHT_STATE_FILE"
          echo "activated"
        fi
        ;;
      *)
        echo "Usage: $0 {active|activate|deactivate|toggle}"
        echo "  active     - Check if spotlight is active (returns true/false)"
        echo "  activate   - Activate spotlight"
        echo "  deactivate - Deactivate spotlight"
        echo "  toggle     - Toggle spotlight state"
        exit 1
        ;;
    esac
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
    spotlight-toggle
    spotlight-overlay
    spotlight-state
    jq # for JSON parsing in scripts
  ];
  wayland.windowManager.hyprland.enable = true;
  wayland.windowManager.hyprland.settings = {
    exec-once = [
      "mako"
      "variety"
      "clipse -listen" # start clipboard manager
      "walker --gapplication-service"
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
      "eDP-1,preferred,auto,1.5"
      "desc:Samsung Display Corp. 0x416D,2880x1800@60.00Hz,auto,2.0"
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
      # make pop-up file dialogs float, stay centred, and avoid oversized layouts
      "float, title:(Open|Progress|Save File)"
      "center, title:(Open|Progress|Save File)"
      "size 1280 900,title:(Open|Progress|Save File)"
      "maxsize 1600 1000,title:(Open|Progress|Save File)"
      "suppressevent maximize,title:(Open|Progress|Save File)"
      "float, class:^(code)$, initialTitle:^(Visual Studio Code)$"
      "center, class:^(code)$, initialTitle:^(Visual Studio Code)$"
      "pin, class:^(code)$, initialTitle:^(Visual Studio Code)$"

      # throw sharing indicators away
      "workspace special silent, title:^(Firefox — Sharing Indicator)$"
      "workspace special silent, title:^(.*is sharing (your screen|a window)\.)$"
      # clipse - clipboard manager
      "float, class:^(clipse)$"
      "size 622 652,class:^(clipse)$"
      # spotlight overlay
      "float, title:^(spotlight-overlay)$"
      "nofocus,title:^(spotlight-overlay)$"
      "noborder,title:^(spotlight-overlay)$"
      "noshadow,title:^(spotlight-overlay)$"
      "noanim,title:^(spotlight-overlay)$"
      "fullscreen,title:^(spotlight-overlay)$"
      "pin,title:^(spotlight-overlay)$"
      "stayfocused,title:^(spotlight-overlay)$"
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
      # Spotlight (locate mouse) - double Ctrl press
      "CTRL, CTRL, exec, spotlight-toggle"
      # Exit spotlight with ESC
      "ESC, exec, spotlight-state deactivate"
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
