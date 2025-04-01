{ pkgs, ... }:
{
  home.stateVersion = "24.11";

  home.packages = with pkgs; [
    rofi-wayland
  ];
  programs.plasma = {
    enable = true;

    #
    # Some high-level settings:
    #
    workspace = {
      clickItemTo = "select"; # clicking item selects it
      lookAndFeel = "org.kde.breezedark.desktop";
      cursor = {
        theme = "Bibata-Modern-Ice";
        size = 32;
      };
      iconTheme = "Papirus-Dark";
    };

    input.keyboard = {
      layouts = [
        { layout = "us"; }
        { layout = "ru"; }
      ];
      repeatDelay = 250;
      repeatRate = 30;
    };

    hotkeys.commands = {
      "launch-konsole" = {
        name = "Launch Terminal";
        key = "Meta+Shift+Return";
        command = "alacritty";
      };
      "rofi" = {
        name = "Rofi";
        key = "Meta+D";
        command = "rofi -show run";
      };
    };

    fonts = {
      general = {
        family = "Hack Mono";
        pointSize = 12;
      };
    };

    panels = [
      # Windows-like panel at the bottom
      {
        location = "bottom";
        widgets = [
          # We can configure the widgets by adding the name and config
          # attributes. For example to add the the kickoff widget and set the
          # icon to "nix-snowflake-white" use the below configuration. This will
          # add the "icon" key to the "General" group for the widget in
          # ~/.config/plasma-org.kde.plasma.desktop-appletsrc.
          {
            name = "org.kde.plasma.kickoff";
            config = {
              General = {
                icon = "nix-snowflake-white";
                alphaSort = true;
              };
            };
          }
          {
            name = "org.kde.plasma.pager";
            config = {
              General = {
                displayedText = "Number";
              };
            };
          }
          # If no configuration is needed, specifying only the name of the
          # widget will add them with the default configuration.
          {
            iconTasks = {
              launchers = [ ];
            };
          }
          "org.kde.plasma.marginsseparator"
          # If you need configuration for your widget, instead of specifying the
          # the keys and values directly using the config attribute as shown
          # above, plasma-manager also provides some higher-level interfaces for
          # configuring the widgets. See modules/widgets for supported widgets
          # and options for these widgets. The widgets below shows two examples
          # of usage, one where we add a digital clock, setting 12h time and
          # first day of the week to Sunday and another adding a systray with
          # some modifications in which entries to show.
          {
            systemTray.items = {
              # We explicitly show bluetooth and battery
              shown = [
                "org.kde.plasma.battery"
                "org.kde.plasma.bluetooth"
                "org.kde.plasma.networkmanagement"
              ];
              # And explicitly hide volume
              hidden = [
                "org.kde.plasma.volume"
              ];
            };
          }
          {
            digitalClock = {
              calendar.firstDayOfWeek = "monday";
              time.format = "24h";
              timeZone = {
                selected = [
                  "Local"
                  "Europe/Moscow"
                  "Europe/London"
                  "America/New_York"
                  "America/Los_Angeles"
                ];
                lastSelected = "Local";
                changeOnScroll = true;
                format = "city";
              };
            };
          }
        ];
        height = 32;
      }
    ];

    powerdevil = {
      AC = {
        powerButtonAction = "lockScreen";
        autoSuspend = {
          action = "nothing";
        };
        turnOffDisplay = {
          idleTimeout = 1000;
          idleTimeoutWhenLocked = "immediately";
        };
        powerProfile = "performance";
      };
      battery = {
        powerButtonAction = "sleep";
        whenSleepingEnter = "standbyThenHibernate";
        autoSuspend = {
          action = "sleep";
          idleTimeout = 600;
        };
        turnOffDisplay = {
          idleTimeout = 300;
          idleTimeoutWhenLocked = "immediately";
        };
        powerProfile = "balanced";
      };
      lowBattery = {
        whenLaptopLidClosed = "hibernate";
        powerProfile = "powerSaving";
        dimDisplay.enable = true;
        turnOffDisplay = {
          idleTimeout = 120;
          idleTimeoutWhenLocked = "immediately";
        };
      };
    };

    kwin = {
      edgeBarrier = 0; # Disables the edge-barriers introduced in plasma 6.1
      cornerBarrier = false;
    };

    kscreenlocker = {
      lockOnResume = true;
      timeout = 10;
    };

    #
    # Some mid-level settings:
    #
    shortcuts = {
      ksmserver = {
        "Lock Session" = [
          "Screensaver"
          "Meta+Ctrl+Alt+L"
        ];
      };

      plasmashell = {
        "activate task manager entry 1" = [ ];
        "activate task manager entry 2" = [ ];
        "activate task manager entry 3" = [ ];
        "activate task manager entry 4" = [ ];
        "activate task manager entry 5" = [ ];
        "activate task manager entry 6" = [ ];
        "activate task manager entry 7" = [ ];
        "activate task manager entry 8" = [ ];
        "activate task manager entry 9" = [ ];
        "activate task manager entry 10" = [ ];
      };

      kwin = {
        "Expose" = "Meta+,";
        "Overview" = "Meta+;";
        "Window Close" = "Meta+W";
        "Window Maximize" = "Meta+Up";
        "Show Desktop" = "Meta+Down";
        "Switch to Desktop 1" = "Meta+1";
        "Switch to Desktop 2" = "Meta+2";
        "Switch to Desktop 3" = "Meta+3";
        "Switch to Desktop 4" = "Meta+4";
        "Switch to Desktop 5" = "Meta+5";
        "Window to Desktop 1" = "Meta+!";
        "Window to Desktop 2" = "Meta+@";
        "Window to Desktop 3" = "Meta+#";
        "Window to Desktop 4" = "Meta+$";
        "Window to Desktop 5" = "Meta+%";
        "Switch One Desktop to the Left" = "Meta+Ctrl+Left";
        "Switch One Desktop to the Right" = "Meta+Ctrl+Right";
      };
      ksmserver = {
        "Log Out" = "Meta+Shift+E";
      };
    };

    #
    # Some low-level settings:
    #
    configFile = {
      baloofilerc."Basic Settings"."Indexing-Enabled" = false;
      kwinrc."org.kde.kdecoration2".ButtonsOnLeft = "SF";
      kwinrc.Desktops.Number = {
        value = 5;
        # Forces kde to not change this value (even through the settings app).
        immutable = true;
      };
      kdeglobals."KDE"."AnimationDurationFactor" = 0;
      kscreenlockerrc = {
        Greeter.WallpaperPlugin = "org.kde.potd";
        # To use nested groups use / as a separator. In the below example,
        # Provider will be added to [Greeter][Wallpaper][org.kde.potd][General].
        "Greeter/Wallpaper/org.kde.potd/General".Provider = "bing";
      };

      plasmarc."OSD"."kbdLayoutChangedEnabled" = false;
    };
  };
}
