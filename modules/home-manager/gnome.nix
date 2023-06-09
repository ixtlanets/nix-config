{ inputs, outputs, lib, config, pkgs, ... }: 
let
  mkTuple = lib.hm.gvariant.mkTuple;
in
{
  home.packages = with pkgs; [
    gnomeExtensions.tray-icons-reloaded
    gnomeExtensions.dash-to-panel
    gnomeExtensions.just-perfection
    gnomeExtensions.caffeine
    gnomeExtensions.bluetooth-quick-connect
    gnomeExtensions.quick-lang-switch
    gnome.gnome-power-manager
  ];
  programs = {
    gnome-terminal = {
      enable = true;
      showMenubar = false;
      themeVariant = "dark";
      profile = {
        "default" = {
          default = true;
          audibleBell = false;
          boldIsBright = true;
          font = "Hack Nerd Font 12";
          loginShell = true;
          showScrollbar = false;
          visibleName = "default";
          colors = {
            backgroundColor = "rgb(23,20,33)";
            foregroundColor = "rgb(208,207,204)";
            palette = [ "rgb(46,52,54)" "rgb(204,0,0)" "rgb(78,154,6)" "rgb(196,160,0)" "rgb(52,101,164)" "rgb(117,80,123)" "rgb(6,152,154)" "rgb(211,215,207)" "rgb(85,87,83)" "rgb(239,41,41)" "rgb(138,226,52)" "rgb(252,233,79)" "rgb(114,159,207)" "rgb(173,127,168)" "rgb(52,226,226)" "rgb(238,238,236)" ];
          };
        };
      };
    };
  };
  dconf.settings = {
    "org/gnome/desktop/interface" = {
      clock-show-weekday = true;
      document-font-name = "Cantarell 12";
      enable-animations = true;
      font-antialiasing = "grayscale";
      font-hinting = "slight";
      font-name = "Cantarell 12";
      locate-pointer = false;
      monospace-font-name = "Hack Nerd Font 14";
      show-battery-percentage = true;
    };
    "org/gnome/desktop/input-sources" = {
      sources = [ (mkTuple [ "xkb" "us" ]) (mkTuple [ "xkb" "ru" ]) ];
      xkb-options = [ "grp:win_space_toggle" "grp:win_space_toggle" ];
    };
    "org/gnome/desktop/wm/keybindings" = {
      close = [ "<Super>q" "<Alt>F4" ];
      maximize = [ "<Super>Up" ];
      unmaximize = [ "<Super>Down" ];
      toggle-fullscreen = [ "<Super>f" ];
      switch-to-workspace-left = [ "<Ctrl><Alt>Left" ];
      switch-to-workspace-right = [ "<Ctrl><Alt>Right" ];
      switch-to-workspace-1 = [ "<Ctrl><Alt>1" ];
      switch-to-workspace-2 = [ "<Ctrl><Alt>2" ];
      switch-to-workspace-3 = [ "<Ctrl><Alt>3" ];
      switch-to-workspace-4 = [ "<Ctrl><Alt>4" ];
      switch-to-workspace-5 = [ "<Ctrl><Alt>5" ];
      move-to-workspace-left = [ "<Shift><Ctrl><Alt>Left" ];
      move-to-workspace-right = [ "<Shift><Ctrl><Alt>Right" ];
      move-to-workspace-1 = [ "<Shift><Ctrl><Alt>1" ];
      move-to-workspace-2 = [ "<Shift><Ctrl><Alt>2" ];
      move-to-workspace-3 = [ "<Shift><Ctrl><Alt>3" ];
      move-to-workspace-4 = [ "<Shift><Ctrl><Alt>4" ];
      move-to-workspace-5 = [ "<Shift><Ctrl><Alt>5" ];
    };
    "org/gnome/settings-daemon/plugins/media-keys" = {
      custom-keybindings = [
        "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom0/"
        "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom1/"
        "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom2/"
      ];
    };
    "org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom0" = {
      binding = "<Super>Return";
      command = "gnome-terminal";
      name = "open-terminal";
    };
    "org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom1" = {
      binding = "<Super>b";
      command = "chromium";
      name = "open-browser";
    };
    "org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom2" = {
      binding = "<Super>e";
      command = "nautilus";
      name = "open-file-browser";
    };
    "org/gnome/shell" = {
      favorite-apps = [
        "chromium-browser.desktop"
        "firefox.desktop"
        "org.gnome.Terminal.desktop"
        "org.gnome.Nautilus.desktop"
        "org.telegram.desktop.desktop"
        "code.desktop"
      ];
      disable-user-extensions = false;
      enabled-extensions = [
        "trayIconsReloaded@selfmade.pl"
        "dash-to-panel@jderose9.github.com"
        "just-perfection-desktop@just-perfection"
        "caffeine@patapon.info"
        "bluetooth-quick-connect@bjarosze.gmail.com"
        "quick-lang-switch@ankostis.gmail.com"
      ];
    };
    "org/gnome/clocks" = {
      world-clocks = "[{'location': <(uint32 2, <('San Francisco', 'KOAK', true, [(0.65832848982162007, -2.133408063190589)], [(0.659296885757089, -2.1366218601153339)])>)>}, {'location': <(uint32 2, <('New York', 'KNYC', true, [(0.71180344078725644, -1.2909618758762367)], [(0.71059804659265924, -1.2916478949920254)])>)>}, {'location': <(uint32 2, <('London', 'EGWU', true, [(0.89971722940307675, -0.007272211034407213)], [(0.89884456477707964, -0.0020362232784242244)])>)>}]";
    };
    "org/gnome/shell/world-clocks" = {
      locations = "[<(uint32 2, <('San Francisco', 'KOAK', true, [(0.65832848982162007, -2.133408063190589)], [(0.659296885757089, -2.1366218601153339)])>)>, <(uint32 2, <('New York', 'KNYC', true, [(0.71180344078725644, -1.2909618758762367)], [(0.71059804659265924, -1.2916478949920254)])>)>, <(uint32 2, <('London', 'EGWU', true, [(0.89971722940307675, -0.007272211034407213)], [(0.89884456477707964, -0.0020362232784242244)])>)>]";
    };
  };
}
