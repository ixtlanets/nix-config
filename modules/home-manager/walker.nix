{
  pkgs,
  ...
}:
{
  home.packages = with pkgs; [
    libqalculate
  ];

  services.cliphist.enable = true;
  services.walker = {
    enable = true;
    systemd.enable = true;
    settings = {
      app_launch_prefix = "env GDK_SCALE=1.5 QT_SCALE_FACTOR=1.5";
      as_window = false;
      close_when_open = false;
      disable_click_to_close = false;
      force_keyboard_focus = true;
      hotreload_theme = false;
      locale = "";
      monitor = "";
      terminal_title_flag = "";
      theme = "default";
      timeout = 0;
      activation_mode = {
        labels = "";
      };
      builtins = {
        applications = {
          context_aware = true;
          hide_actions_with_empty_query = true;
          history = true;
          icon = "applications-other";
          name = "applications";
          placeholder = "Applications";
          prioritize_new = true;
          refresh = true;
          show_generic = true;
          show_icon_when_single = true;
          show_sub_when_single = true;
          weight = 5;
          actions = {
            enabled = true;
            hide_category = false;
            hide_without_query = true;
          };
        };
        calc = {
          hidden = true;
          icon = "accessories-calculator";
          min_chars = 4;
          name = "calc";
          placeholder = "Calculator";
          require_number = true;
          prefix = "=";
          weight = 5;
        };
        clipboard = {
          always_put_new_on_top = true;
          avoid_line_breaks = true;
          exec = "wl-copy";
          image_height = 200;
          max_entries = 10;
          name = "clipboard";
          placeholder = "Clipboard";
          prefix = ":";
          weight = 5;
        };
        dmenu = {
          hidden = true;
          name = "dmenu";
          placeholder = "Dmenu";
          show_icon_when_single = true;
          switcher_only = true;
          weight = 5;
        };
        emojis = {
          hidden = true;
          exec = "wl-copy";
          history = true;
          name = "emojis";
          placeholder = "Emojis";
          show_unqualified = false;
          switcher_only = true;
          typeahead = true;
          weight = 5;
          prefix = ".";
        };
      };
    };
  };
}
