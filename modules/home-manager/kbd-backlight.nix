{ pkgs, ... }:
{
  config = {
    home.packages = [
      (pkgs.writeShellScriptBin "kbd-backlight" ''
            #!/bin/sh

            # Find the keyboard backlight device
            for device in $(light -L | grep "kbd_backlight" | sed 's/.*sysfs\/leds\///')
            do
              KBD_DEVICE="sysfs/leds/$device"
              break
            done

            if [ -z "$KBD_DEVICE" ]; then
              echo "No keyboard backlight device found"
              exit 1
            fi

            if [ "$1" = "up" ]; then
              light -Ars "$KBD_DEVICE" 50
            elif [ "$1" = "down" ]; then
              light -Urs "$KBD_DEVICE" 50
            elif [ "$1" = "toggle" ]; then
              if [ "$(light -rs "$KBD_DEVICE")" = "0" ]; then
                light -Srs "$KBD_DEVICE" 100
              else
                light -Srs "$KBD_DEVICE" 0
              fi
            fi
          '')
    ];
  };
}
