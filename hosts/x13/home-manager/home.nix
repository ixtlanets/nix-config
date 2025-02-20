# This is your home-manager configuration file
# Use this to configure your home environment (it replaces ~/.config/nixpkgs/home.nix)

{
  pkgs,
  dpi,
  ...
}:
let
kbd-backlight = pkgs.writeShellScriptBin "kbd-backlight" ''
    #!/usr/bin/env nix-shell
    current=$(cat /sys/class/leds/asus::kbd_backlight/brightness)
    max=3
    next=$(((current + 1) % (max + 1)))
    echo $next | tee /sys/class/leds/asus::kbd_backlight/brightness
  '';

  setup-mobile-workspace = pkgs.writeShellScriptBin "setup-mobile-workspace" ''
      ${pkgs.variety}/bin/variety --next
      ${pkgs.hyprland}/bin/hyprctl keyword workspace r1-5, monitor:eDP-1,persistent:true
      ${pkgs.hyprland}/bin/hyprctl keyword workspace r10, monitor:eDP-1,persistent:true
      ${pkgs.hyprland}/bin/hyprctl dispatch moveworkspacetomonitor 1 eDP-1
      ${pkgs.hyprland}/bin/hyprctl dispatch moveworkspacetomonitor 2 eDP-1
      ${pkgs.hyprland}/bin/hyprctl dispatch moveworkspacetomonitor 3 eDP-1
      ${pkgs.hyprland}/bin/hyprctl dispatch moveworkspacetomonitor 4 eDP-1
      ${pkgs.hyprland}/bin/hyprctl dispatch moveworkspacetomonitor 5 eDP-1
      ${pkgs.hyprland}/bin/hyprctl dispatch moveworkspacetomonitor 10 eDP-1
    '';

    setup-docked-home-workspace = pkgs.writeShellScriptBin "setup-docked-home-workspace" ''
      ${pkgs.variety}/bin/variety --next
      ${pkgs.hyprland}/bin/hyprctl keyword workspace r1-5, monitor:DP-1,persistent:true
      ${pkgs.hyprland}/bin/hyprctl keyword workspace r10, monitor:eDP-1,persistent:true
      ${pkgs.hyprland}/bin/hyprctl dispatch moveworkspacetomonitor 1 DP-1
      ${pkgs.hyprland}/bin/hyprctl dispatch moveworkspacetomonitor 2 DP-1
      ${pkgs.hyprland}/bin/hyprctl dispatch moveworkspacetomonitor 3 DP-1
      ${pkgs.hyprland}/bin/hyprctl dispatch moveworkspacetomonitor 4 DP-1
      ${pkgs.hyprland}/bin/hyprctl dispatch moveworkspacetomonitor 5 DP-1
      ${pkgs.hyprland}/bin/hyprctl dispatch moveworkspacetomonitor 10 eDP-1
    '';

    setup-docked-sg-workspace = pkgs.writeShellScriptBin "setup-docked-sg-workspace" ''
      ${pkgs.variety}/bin/variety --next
      ${pkgs.hyprland}/bin/hyprctl keyword workspace r1-5, monitor:DP-2,persistent:true
      ${pkgs.hyprland}/bin/hyprctl keyword workspace r10, monitor:eDP-1,persistent:true
      ${pkgs.hyprland}/bin/hyprctl dispatch moveworkspacetomonitor 1 DP-2
      ${pkgs.hyprland}/bin/hyprctl dispatch moveworkspacetomonitor 2 DP-2
      ${pkgs.hyprland}/bin/hyprctl dispatch moveworkspacetomonitor 3 DP-2
      ${pkgs.hyprland}/bin/hyprctl dispatch moveworkspacetomonitor 4 DP-2
      ${pkgs.hyprland}/bin/hyprctl dispatch moveworkspacetomonitor 5 DP-2
      ${pkgs.hyprland}/bin/hyprctl dispatch moveworkspacetomonitor 10 eDP-1
    '';
in
{
  home.sessionVariables = {
    WIFI_INTERFACE = "wlp6s0";
    HWMON_PATH = "/sys/devices/virtual/thermal/thermal_zone0/hwmon5/temp1_input";
    THERMAL_ZONE = "0";
    BACKLIGHT_CARD = "amdgpu_bl0";
  };
  # You can import other home-manager modules here
  imports = [
    ../../../modules/home-manager/starship.nix
    ../../../modules/home-manager/tmux.nix
    ../../../modules/home-manager/common.nix
    ../../../modules/home-manager/services.nix
    ../../../modules/home-manager/kanshi.nix
    ../../../modules/home-manager/emacs.nix
    ../../../modules/home-manager/linux-desktop.nix
    ../../../modules/home-manager/gnome.nix
    ../../../modules/home-manager/hyprland.nix
    ../../../modules/home-manager/waybar.nix
    ../../../modules/home-manager/email.nix
    ../../../modules/home-manager/nvim.nix
    ../../../modules/home-manager/ghostty.nix
  ];

  wayland.windowManager.hyprland.settings = {
    monitor = [
      "eDP-1,1920x1200@60.000Hz,auto,1.5"
      "HDMI-A-1,2560x1440@144.000Hz,auto,1.6"
      "DP-1,3840x2560@60.000Hz,auto,2.0"
      "DP-2,3840x2560@60.000Hz,auto,2.0"
    ];
    bindl = [
      ", switch:on:Lid Switch, exec, hyprctl keyword monitor \"eDP-1, disable\""
      ", switch:off:Lid Switch, exec, hyprctl keyword monitor \"eDP-1, 1920x1200, 0x0, 1.5\""
    ];
    bind = [
      "ALT, space, exec, kbd-backlight"
    ];
  };
  services.kanshi.settings = [
    {
      profile = {
        name = "mobile";
        outputs = [
          {
            criteria = "eDP-1";
            mode = "1920x1200@60.000Hz";
            scale = 1.5;
          }
        ];
        exec = ["setup-mobile-workspace"];
      };
    }
    {
      profile = {
        name = "dockedHome";
        exec = ["setup-docked-home-workspace"];
        outputs = [
          {
            criteria = "eDP-1";
            mode = "1920x1200@60.000Hz";
            scale = 1.5;
          }
          {
            criteria = "DP-1";
            mode = "2560x1440@144.000Hz";
            scale = 1.6;
          }
        ];
      };
    }
    {
      profile = {
        name = "dockedSG";
        exec = ["setup-docked-sg-workspace"];
        outputs = [
          {
            criteria = "eDP-1";
            mode = "1920x1200@60.000Hz";
            scale = 1.5;
          }
          {
            criteria = "DP-2";
            mode = "3840x2560@60.000Hz";
            scale = 2.0;
          }
        ];
      };
    }
  ];
  dconf.settings = {
    "org/gnome/desktop/interface" = {
      text-scaling-factor = 1.0;
    };
  };
  home = {
    username = "nik";
    homeDirectory = "/home/nik";
  };

  home.packages = with pkgs; [
    asusctl
    supergfxctl
    nvtop
    kbd-backlight
    setup-mobile-workspace
    setup-docked-home-workspace
    setup-docked-sg-workspace
  ];

  xresources.properties = {
    "Xft.dpi" = dpi;
  };

  # https://nixos.wiki/wiki/FAQ/When_do_I_update_stateVersion
  home.stateVersion = "24.11";
}
