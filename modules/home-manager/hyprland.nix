{ pkgs
, lib
, dpi
, ...
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

    ${pkgs.coreutils}/bin/mkdir -p "$OUTPUT_DIR"

    ${pkgs.procps}/bin/pkill slurp || hyprshot -m region --raw |
      satty --filename - \
        --output-filename "$OUTPUT_DIR/screenshot-$(${pkgs.coreutils}/bin/date +'%Y-%m-%d_%H-%M-%S').png" \
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
        printf "[M]\n"
        ;;
      master)
        printf "[T]\n"
        ;;
      *)
        printf "[?] %s\n" "$layout"
        ;;
    esac
  '';
  hyprlock-caps-lock = pkgs.writeShellScriptBin "hyprlock-caps-lock" ''
    set -euo pipefail

    devices="$(${pkgs.hyprland}/bin/hyprctl -j devices 2>/dev/null || true)"
    [ -n "$devices" ] || exit 0

    if printf '%s' "$devices" | ${pkgs.jq}/bin/jq -e '(.keyboards // []) | any(.capsLock == true)' >/dev/null; then
      printf "CAPS LOCK\n"
    fi
  '';
  hypr-lid-apply = pkgs.writeShellScriptBin "hypr-lid-apply" ''
    set -euo pipefail

    hyprctl_bin="${pkgs.hyprland}/bin/hyprctl"
    jq_bin="${pkgs.jq}/bin/jq"
    systemctl_bin="${pkgs.systemd}/bin/systemctl"

    inhibitor_unit="hypr-lid-docked-inhibitor.service"
    release_timer_unit="hypr-lid-docked-inhibitor-release.timer"

    internal_monitor="''${HYPR_INTERNAL_MONITOR:-eDP-1}"
    internal_scale="''${HYPR_INTERNAL_MONITOR_SCALE:-1.5}"
    policy="''${HYPR_INTERNAL_MONITOR_POLICY:-lid-docked}"

    lid_closed() {
      local state_file

      for state_file in /proc/acpi/button/lid/*/state; do
        [ -r "$state_file" ] || continue

        case "$(${pkgs.coreutils}/bin/tr '[:upper:]' '[:lower:]' < "$state_file")" in
          *closed*)
            return 0
            ;;
        esac
      done

      return 1
    }

    start_release_timer() {
      if $systemctl_bin --user is-active --quiet "$release_timer_unit"; then
        return 0
      fi

      $systemctl_bin --user reset-failed "$release_timer_unit" >/dev/null 2>&1 || true
      $systemctl_bin --user start "$release_timer_unit" >/dev/null 2>&1 || true
    }

    monitors_json="$($hyprctl_bin -j monitors all)"
    detected_internal="$({ printf '%s' "$monitors_json" | $jq_bin -r 'map(select(.name | test("^eDP"))) | if length > 0 then .[0].name else empty end'; } || true)"

    if [ -n "$detected_internal" ]; then
      internal_monitor="$detected_internal"
    fi

    external_count="$(printf '%s' "$monitors_json" | $jq_bin '[.[] | select(((.name | test("^eDP")) | not) and ((.disabled // false) == false))] | length')"
    internal_disabled="$(printf '%s' "$monitors_json" | $jq_bin -r --arg internal "$internal_monitor" '([.[] | select(.name == $internal) | (.disabled // false)] | .[0]) // false')"

    if [ "$policy" = "external-only" ]; then
      if [ "$external_count" -gt 0 ]; then
        desired_internal_state="disabled"
      else
        desired_internal_state="enabled"
      fi
    else
      if [ "$external_count" -gt 0 ] && lid_closed; then
        desired_internal_state="disabled"
      else
        desired_internal_state="enabled"
      fi
    fi

    if [ "$desired_internal_state" = "disabled" ] && [ "$internal_disabled" != "true" ]; then
      $hyprctl_bin keyword monitor "$internal_monitor,disable" >/dev/null
    fi

    if [ "$desired_internal_state" = "enabled" ] && [ "$internal_disabled" != "false" ]; then
      $hyprctl_bin keyword monitor "$internal_monitor,preferred,auto,$internal_scale" >/dev/null
    fi

    if [ "$external_count" -gt 0 ]; then
      if ! lid_closed; then
        $systemctl_bin --user stop "$release_timer_unit" >/dev/null 2>&1 || true
      fi
      $systemctl_bin --user start "$inhibitor_unit" >/dev/null 2>&1 || true
    elif lid_closed; then
      if $systemctl_bin --user is-active --quiet "$inhibitor_unit"; then
        start_release_timer
      fi
    else
      $systemctl_bin --user stop "$release_timer_unit" >/dev/null 2>&1 || true
      $systemctl_bin --user stop "$inhibitor_unit" >/dev/null 2>&1 || true
    fi
  '';
  hypr-lid-monitor = pkgs.writeShellScriptBin "hypr-lid-monitor" ''
    set -euo pipefail

    ${hypr-lid-apply}/bin/hypr-lid-apply

    ${pkgs.socat}/bin/socat - "UNIX-CONNECT:$XDG_RUNTIME_DIR/hypr/$HYPRLAND_INSTANCE_SIGNATURE/.socket2.sock" \
      | while read -r line; do
          case "$line" in
            monitoradded*|monitorremoved*)
              ${hypr-lid-apply}/bin/hypr-lid-apply
              ;;
          esac
        done
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
    thunar
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
    hypr-lid-apply
    hypr-lid-monitor
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
      "hypr-lid-monitor"
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
      # keep transient portal/file chooser dialogs out of the tiling layout
      "float on, match:title ^(Select what to share)$"
      "center on, match:title ^(Select what to share)$"
      "pin on, match:title ^(Select what to share)$"
      "size 1400 920, match:title ^(Select what to share)$"
      "max_size 1800 1100, match:title ^(Select what to share)$"
      "suppress_event maximize, match:title ^(Select what to share)$"
      "float on, match:title ^(Open|Open File|Open Files|Progress|Save File|Save As|Select Folder|Choose Files?|File Upload|Choose what to share)$"
      "center on, match:title ^(Open|Open File|Open Files|Progress|Save File|Save As|Select Folder|Choose Files?|File Upload|Choose what to share)$"
      "size 1280 900, match:title ^(Open|Open File|Open Files|Progress|Save File|Save As|Select Folder|Choose Files?|File Upload|Choose what to share)$"
      "max_size 1600 1000, match:title ^(Open|Open File|Open Files|Progress|Save File|Save As|Select Folder|Choose Files?|File Upload|Choose what to share)$"
      "suppress_event maximize, match:title ^(Open|Open File|Open Files|Progress|Save File|Save As|Select Folder|Choose Files?|File Upload|Choose what to share)$"
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
      ", switch:on:Lid Switch, exec, hypr-lid-apply"
      ", switch:off:Lid Switch, exec, hypr-lid-apply"
    ];
    bind = [
      "$mod+SHIFT, E, exit"
      "$mod, W, killactive"
      "$mod, F, togglefloating"
      "$mod, B, exec, chromium-browser"
      "$mod, E, exec, thunar"
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
        builtins.genList
          (
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

  catppuccin.hyprlock.useDefaultConfig = false;

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

      label = [
        {
          text = "cmd[update:1000] date +%H:%M";
          color = "rgba(205, 214, 244, 1.0)";
          font_size = 96;
          font_family = "JetBrainsMono Nerd Font";
          position = "0, 120";
          halign = "center";
          valign = "center";
        }
        {
          text = "cmd[update:60000] date '+%A, %d %B'";
          color = "rgba(186, 194, 222, 1.0)";
          font_size = 20;
          font_family = "JetBrainsMono Nerd Font";
          position = "0, 45";
          halign = "center";
          valign = "center";
        }
        {
          text = "$LAYOUT";
          color = "rgba(137, 180, 250, 1.0)";
          font_size = 14;
          font_family = "JetBrainsMono Nerd Font";
          position = "0, -105";
          halign = "center";
          valign = "center";
        }
        {
          text = "cmd[update:250] ${hyprlock-caps-lock}/bin/hyprlock-caps-lock";
          color = "rgba(250, 179, 135, 1.0)";
          font_size = 16;
          font_family = "JetBrainsMono Nerd Font";
          position = "0, -140";
          halign = "center";
          valign = "center";
        }
      ];

      input-field = {
        size = "360, 60";
        outline_thickness = 2;
        dots_size = 0.25;
        dots_spacing = 0.3;
        dots_center = true;
        outer_color = "rgba(137, 180, 250, 0.8)";
        inner_color = "rgba(30, 30, 46, 0.85)";
        font_color = "rgba(205, 214, 244, 1.0)";
        fade_on_empty = false;
        placeholder_text = "<i>Password</i>";
        hide_input = false;
        check_color = "rgba(249, 226, 175, 1.0)";
        fail_color = "rgba(243, 139, 168, 1.0)";
        fail_text = "<i>Authentication failed</i>";
        capslock_color = "rgba(250, 179, 135, 1.0)";
        position = "0, -55";
        halign = "center";
        valign = "center";
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

  # Fix swayosd to start after Hyprland is ready
  systemd.user.services.swayosd = {
    Unit = {
      After = lib.mkForce [
        "graphical-session.target"
        "wayland-session.target"
      ];
      PartOf = lib.mkForce [ "graphical-session.target" ];
    };
    Service = {
      ExecStartPre = "${pkgs.coreutils}/bin/sleep 2";
      RestartSec = lib.mkForce "5";
      StartLimitBurst = lib.mkForce 10;
      StartLimitIntervalSec = lib.mkForce "60";
    };
  };

  systemd.user.services.hypr-lid-docked-inhibitor = {
    Unit.Description = "Ignore lid sleep while docked";
    Service.ExecStart = "${pkgs.systemd}/bin/systemd-inhibit --what=handle-lid-switch --why=External-monitor-connected ${pkgs.coreutils}/bin/sleep infinity";
  };

  systemd.user.services.hypr-lid-docked-inhibitor-release = {
    Unit.Description = "Release docked lid inhibitor";
    Service = {
      Type = "oneshot";
      ExecStart = pkgs.writeShellScript "hypr-lid-docked-inhibitor-release" ''
        set -euo pipefail

        external_count=0

        for status_file in /sys/class/drm/*/status; do
          [ -r "$status_file" ] || continue

          connector="''${status_file%/status}"
          connector="''${connector##*/}"

          case "$connector" in
            *-eDP-*|*-eDP)
              continue
              ;;
          esac

          if [ "$(<"$status_file")" = "connected" ]; then
            external_count=$((external_count + 1))
          fi
        done

        if [ "$external_count" -gt 0 ]; then
          exit 0
        fi

        ${pkgs.systemd}/bin/systemctl --user stop hypr-lid-docked-inhibitor.service

        for state_file in /proc/acpi/button/lid/*/state; do
          [ -r "$state_file" ] || continue

          case "$(${pkgs.coreutils}/bin/tr '[:upper:]' '[:lower:]' < "$state_file")" in
            *closed*)
              ${pkgs.systemd}/bin/systemctl suspend || true
              exit 0
              ;;
          esac
        done
      '';
    };
  };

  systemd.user.timers.hypr-lid-docked-inhibitor-release = {
    Unit = {
      Description = "Grace period before lid sleep resumes";
      StartLimitIntervalSec = 0;
    };
    Timer = {
      AccuracySec = "1s";
      OnActiveSec = "15s";
      Unit = "hypr-lid-docked-inhibitor-release.service";
    };
  };

  # Electron Flags File
  home.file.".config/electron-flags.conf".text = ''
    --enable-features=WaylandWindowDecorations
    --ozone-platform-hint=auto
  '';
}
