{
  pkgs,
  dpi,
  ...
}:
let
  DPI = builtins.toString dpi;
  rofi_width = builtins.toString (dpi * 5);
  rofi_height = builtins.toString (dpi * 3);
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
  toggle-layout-mode = pkgs.writeShellScriptBin "toggle-layout-mode" ''
    set -euo pipefail

    current_layout="$(${pkgs.hyprland}/bin/hyprctl -j getoption general:layout | ${pkgs.jq}/bin/jq -r '.str')"

    if [ "$current_layout" = "monocle" ]; then
      ${pkgs.hyprland}/bin/hyprctl keyword general:layout "master" >/dev/null
    else
      ${pkgs.hyprland}/bin/hyprctl keyword general:layout "monocle" >/dev/null
    fi

    ${pkgs.procps}/bin/pkill -RTMIN+8 waybar || true
  '';
  hypr-layout-waybar = pkgs.writeShellScriptBin "hypr-layout-waybar" ''
    set -euo pipefail

    layout="$(${pkgs.hyprland}/bin/hyprctl -j getoption general:layout | ${pkgs.jq}/bin/jq -r '.str')"

    case "$layout" in
      monocle)
        printf "[M] monocle\n"
        ;;
      master)
        printf "[T] master\n"
        ;;
      *)
        printf "[?] %s\n" "$layout"
        ;;
    esac
  '';
in
{
  imports = [
    ./kbd-backlight.nix
  ];
  home.packages = with pkgs; [
    rofi
    rofi-calc
    rofi-emoji
    socat
    adwaita-icon-theme
    adwaita-qt
    grimblast # screenshot utility based on grim
    slurp # Select a region in a Wayland compositor
    hyprshot # take screenshots in Hyprland using your mouse
    xdg-utils # for opening default programs when clicking links
    glfw
    pavucontrol # volume control
    swaybg # to set wallpaper
    clipse # clipboard manager
    wiremix # TUI for audio
    satty # Screenshot annotaion
    handle_monitor_connect
    take-screenshot
    toggle-layout-mode
    hypr-layout-waybar
    hyprpolkitagent
  ];
  xdg.configFile."rofi/config.rasi".text =
    builtins.replaceStrings [ "DPI" "WIDTH" "HEIGHT" ] [ DPI rofi_width rofi_height ]
      (builtins.readFile ../../dotfiles/rofi);
  wayland.windowManager.hyprland.enable = true;
  wayland.windowManager.hyprland.settings = {
    exec-once = [
      "mako"
      "variety"
      "clipse -listen" # start clipboard manager
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
    xwayland = {
      force_zero_scaling = true;
    };
    misc = {
      anr_missed_pings = 5;
    };
    animations = {
      enabled = false;
    };
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
    windowrule = [
      "float on, match:class ^(1Password)$"
      "stay_focused on, match:title ^(Quick Access — 1Password)$"
      "dim_around on, match:title ^(Quick Access — 1Password)$"
      "no_anim on, match:title ^(Quick Access — 1Password)$"

      "float on, match:class ^(org.gnome.*)$"
      "float on, match:class (Wiremix|org.gnome.NautilusPreviewer|com.gabm.satty|TUI.float)"
      "float on, match:class ^(pavucontrol|com.saivert.pwvucontrol)$"
      # make pop-up file dialogs float, stay centred, and avoid oversized layouts
      "float on, match:title (Open|Progress|Save File)"
      "center on, match:title (Open|Progress|Save File)"
      "size 1280 900, match:title (Open|Progress|Save File)"
      "max_size 1600 1000, match:title (Open|Progress|Save File)"
      "suppress_event maximize, match:title (Open|Progress|Save File)"
      "float on, match:class ^(code)$, match:initial_title ^(Visual Studio Code)$"
      "center on, match:class ^(code)$, match:initial_title ^(Visual Studio Code)$"
      "pin on, match:class ^(code)$, match:initial_title ^(Visual Studio Code)$"

      # throw sharing indicators away
      "workspace special silent, match:title ^(Firefox — Sharing Indicator)$"
      "workspace special silent, match:title ^(.*is sharing (your screen|a window)\.)$"
      # clipse - clipboard manager
      "float on, match:class ^(clipse)$"
      "size 622 652, match:class ^(clipse)$"
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
      "$mod, Return, exec, wezterm"
      "$mod, D, exec, rofi -show drun"
      "$mod, H, movefocus, l"
      "$mod, J, movefocus, d"
      "$mod, K, movefocus, u"
      "$mod, L, movefocus, r"
      "$mod+CTRL, H, resizeactive, -10 0"
      "$mod+CTRL, J, resizeactive, 0 -10"
      "$mod+CTRL, K, resizeactive, 0 10"
      "$mod+CTRL, L, resizeactive, 10 0"
      "$mod, G, exec, toggle-layout-mode"
      "$mod+SHIFT, J, layoutmsg, cycleprev"
      "$mod+SHIFT, K, layoutmsg, cyclenext"
      "$mod+SHIFT, S, exec, take-screenshot"
      "$mod+SHIFT, T, exec, fix-text"
      ",XF86AudioRaiseVolume, exec, swayosd-client --output-volume raise"
      ",XF86AudioLowerVolume, exec, swayosd-client --output-volume lower"
      ",XF86AudioMute, exec, swayosd-client --output-volume mute-toggle"
      ",XF86AudioMicMute, exec, swayosd-client --input-volume mute-toggle"
      "$mod, V, exec, wezterm start --class clipse -- clipse"
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
          modules-right = [
            "custom/hyprlayout"
            "hyprland/language"
          ];

          "hyprland/workspaces" = {
          };
          "custom/hyprlayout" = {
            "exec" = "hypr-layout-waybar";
            "signal" = 8;
            "tooltip" = false;
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
