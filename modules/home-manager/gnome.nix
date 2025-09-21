{
  lib,
  pkgs,
  ...
}:
let
  mkTuple = lib.hm.gvariant.mkTuple;
  workspaceNumbers = lib.range 1 9;
  workspaceKeybindings =
    lib.foldl'
      (acc: num:
        let
          key = builtins.toString num;
        in
        acc
        // {
          "switch-to-workspace-${key}" = [
            "<Super>${key}"
            "<Ctrl><Alt>${key}"
          ];
          "move-to-workspace-${key}" = [
            "<Super><Shift>${key}"
            "<Shift><Ctrl><Alt>${key}"
          ];
        }
      )
      {}
      workspaceNumbers;
  appSwitcherDisable = lib.listToAttrs (
    map (num: {
      name = "switch-to-application-${builtins.toString num}";
      value = [ ];
    }) workspaceNumbers
  );
in
{
  imports = [
    ./kbd-backlight.nix
  ];
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
    gnomeExtensions.just-perfection
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
    "org/gnome/desktop/wm/keybindings" =
      workspaceKeybindings
      // {
        close = [
          "<Super>w"
          "<Alt>F4"
        ];
        maximize = [ "<Super>Up" ];
        unmaximize = [ "<Super>Down" ];
        toggle-fullscreen = [ "<Super>f" ];
        switch-to-workspace-left = [ "<Ctrl><Alt>Left" ];
        switch-to-workspace-right = [ "<Ctrl><Alt>Right" ];
        move-to-workspace-left = [ "<Shift><Ctrl><Alt>Left" ];
        move-to-workspace-right = [ "<Shift><Ctrl><Alt>Right" ];
        activate-window-menu = [ ]; # Disable Alt+Space for window menu
      };
    "org/gnome/shell/keybindings" = appSwitcherDisable;
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
    "org/gnome/mutter" = {
      dynamic-workspaces = false;
    };
    "org/gnome/desktop/wm/preferences" = {
      num-workspaces = lib.hm.gvariant.mkUint32 9;
      workspace-names = lib.hm.gvariant.mkArray
        lib.hm.gvariant.type.string
        [
          "1"
          "2"
          "3"
          "4"
          "5"
          "6"
          "7"
          "8"
          "9"
        ];
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
        "appindicatorsupport@rgcjonas.gmail.com"
        "trayIconsReloaded@selfmade.pl"
        "just-perfection-desktop@just-perfection"
        "caffeine@patapon.info"
        "bluetooth-quick-connect@bjarosze.gmail.com"
        "quick-lang-switch@ankostis.gmail.com"
        "dash-to-panel@jderose9.github.com"
      ];
    };
    "org/gnome/shell/extensions/just-perfection" = {
      workspace-animation = false;
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
