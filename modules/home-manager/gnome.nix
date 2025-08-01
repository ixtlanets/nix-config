{
  lib,
  pkgs,
  ...
}:
let
  mkTuple = lib.hm.gvariant.mkTuple;
in
{
  home.sessionVariables = {
    NIXOS_OZONE_WL = "1";
    XCURSOR_SIZE = "24";
  };
  home.packages = with pkgs; [
    gnomeExtensions.appindicator
    gnomeExtensions.caffeine
    gnomeExtensions.bluetooth-quick-connect
    gnomeExtensions.quick-lang-switch
    gnomeExtensions.dash-to-panel
  ];
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
      sources = [
        (mkTuple [
          "xkb"
          "us"
        ])
        (mkTuple [
          "xkb"
          "ru"
        ])
      ];
      xkb-options = [
        "grp:win_space_toggle"
        "grp:win_space_toggle"
      ];
    };
    "org/gnome/desktop/wm/keybindings" = {
      close = [
        "<Super>q"
        "<Alt>F4"
      ];
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
      activate-window-menu = [ ]; # Disable Alt+Space for window menu
    };
    "org/gnome/settings-daemon/plugins/media-keys" = {
      custom-keybindings = [
        "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom0/"
        "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom1/"
        "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom2/"
        "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom3/"
      ];
    };
    "org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom0" = {
      binding = "<Super>Return";
      command = "ghostty";
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
    "org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom3" = {
      binding = "<Alt>space";
      command = "kbd-backlight toggle";
      name = "toggle-keyboard-backlight";
    };
    "org/gnome/shell" = {
      favorite-apps = [
        "brave-browser.desktop"
        "Ghostty.desktop"
        "org.gnome.Nautilus.desktop"
        "org.telegram.desktop.desktop"
        "code.desktop"
      ];
      disable-user-extensions = false;
      enabled-extensions = [
        "trayIconsReloaded@selfmade.pl"
        "just-perfection-desktop@just-perfection"
        "caffeine@patapon.info"
        "bluetooth-quick-connect@bjarosze.gmail.com"
        "quick-lang-switch@ankostis.gmail.com"
        "dash-to-panel@jderose9.github.com"
      ];
    };
    "org/gnome/clocks" = {
      world-clocks = "[{'location': <(uint32 2, <('San Francisco', 'KOAK', true, [(0.65832848982162007, -2.133408063190589)], [(0.659296885757089, -2.1366218601153339)])>)>}, {'location': <(uint32 2, <('New York', 'KNYC', true, [(0.71180344078725644, -1.2909618758762367)], [(0.71059804659265924, -1.2916478949920254)])>)>}, {'location': <(uint32 2, <('London', 'EGWU', true, [(0.89971722940307675, -0.007272211034407213)], [(0.89884456477707964, -0.0020362232784242244)])>)>}]";
    };
    "org/gnome/shell/world-clocks" = {
      locations = "[<(uint32 2, <('San Francisco', 'KOAK', true, [(0.65832848982162007, -2.133408063190589)], [(0.659296885757089, -2.1366218601153339)])>)>, <(uint32 2, <('New York', 'KNYC', true, [(0.71180344078725644, -1.2909618758762367)], [(0.71059804659265924, -1.2916478949920254)])>)>, <(uint32 2, <('London', 'EGWU', true, [(0.89971722940307675, -0.007272211034407213)], [(0.89884456477707964, -0.0020362232784242244)])>)>]";
    };
    "org/gnome/desktop/peripherals/keyboard" = {
      repeat = lib.hm.gvariant.mkUint32 30;
      delay = lib.hm.gvariant.mkUint32 250;
      repeat-enabled = true;
    };

  };
  home.file.".config/electron-flags.conf".text = ''
    --enable-features=WaylandWindowDecorations
    --ozone-platform-hint=auto
  '';
}
