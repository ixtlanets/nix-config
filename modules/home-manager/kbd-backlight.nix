{ pkgs, ... }:
{
  config = {
    home.packages = [
      (pkgs.writeShellScriptBin "kbd-backlight" ''
        #!/bin/sh
        set -eu

        brightnessctl_bin="${pkgs.brightnessctl}/bin/brightnessctl"
        awk_bin="${pkgs.gawk}/bin/awk"

        kbd_device="$($brightnessctl_bin -l | $awk_bin -F"'" '/::kbd_backlight/ { print $2; exit }')"

        if [ -z "$kbd_device" ]; then
          echo "No keyboard backlight device found"
          exit 1
        fi

        current="$($brightnessctl_bin -d "$kbd_device" g)"
        max="$($brightnessctl_bin -d "$kbd_device" m)"

        case "''${1:-toggle}" in
          up)
            next=$((current + 1))
            if [ "$next" -gt "$max" ]; then
              next="$max"
            fi
            $brightnessctl_bin -d "$kbd_device" s "$next" >/dev/null
            ;;
          down)
            next=$((current - 1))
            if [ "$next" -lt 0 ]; then
              next=0
            fi
            $brightnessctl_bin -d "$kbd_device" s "$next" >/dev/null
            ;;
          toggle)
            if [ "$current" -eq 0 ]; then
              $brightnessctl_bin -d "$kbd_device" s "$max" >/dev/null
            else
              $brightnessctl_bin -d "$kbd_device" s 0 >/dev/null
            fi
            ;;
          *)
            echo "Usage: kbd-backlight [up|down|toggle]"
            exit 2
            ;;
        esac
      '')
    ];
  };
}
