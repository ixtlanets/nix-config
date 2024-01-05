
{ inputs, outputs, lib, config, pkgs, dpi, ... }: 
let
  DPI = builtins.toString dpi;
  rofi_width = (builtins.toString(dpi * 5));
  rofi_height = (builtins.toString(dpi * 3));
  polybar_height = (builtins.toString(dpi * 0.1666));
in
{
  home.packages = with pkgs; [
      xclip
      nerdfonts
      wl-clipboard
      variety
      zathura
      brightnessctl
      pamixer
      wireplumber
      swaybg
      mpv
      liberation_ttf
      font-awesome
      ];


  programs = {
    alacritty = {
      enable = true;
      settings = {
        env.TERM = "xterm-256color";
        font = {
          normal.family = "Hack Nerd Font";
          size = 14;
        };
      };
    };
    vscode = {
      enable = true;
      package = pkgs.vscode.fhs;
      extensions = with pkgs.vscode-extensions; [
        catppuccin.catppuccin-vsc
          dbaeumer.vscode-eslint
          bbenoist.nix
          jnoortheen.nix-ide
          github.copilot
          github.vscode-pull-request-github
          github.codespaces
      ];
    };
    browserpass = {
      enable = true;
      browsers = [
          "firefox"
          "chromium"
      ];
    };
    firefox = {
      enable = true;
    };
    chromium = {
      enable = true;
      commandLineArgs = [
        "--ozone-platform-hint=auto"
      ];
      extensions = [
      { id = "cjpalhdlnbpafiamejdnhcphjbkeiagm"; } # ublock origin
      { id = "aeblfdkhhhdcdjpifhhbdiojplfjncoa"; } # 1Password
      { id = "mbmgnelfcpoecdepckhlhegpcehmpmji"; } # SponsorBlock for YouTube - Skip Sponsorships
      { id = "kcpnkledgcbobhkgimpbmejgockkplob"; } # Tracking Token Stripper
      { id = "gebbhagfogifgggkldgodflihgfeippi"; } # Return YouTube Dislike
      { id = "naepdomgkenhinolocfifgehidddafch"; } # Browserpass
      { id = "enamippconapkdmgfgjchkhakpfinmaj"; } # DeArrow. dearrow.ajay.app
      { id = "fcphghnknhkimeagdglkljinmpbagone"; } # YouTube AutoHD. preselect video resolution
      { id = "hipekcciheckooncpjeljhnekcoolahp"; } # Tabliss - A Beautiful New Tab
      {
        id = "dcpihecpambacapedldabdbpakmachpb";
        updateUrl = "https://raw.githubusercontent.com/iamadamdev/bypass-paywalls-chrome/master/src/updates/updates.xml";
      }
      ];
    };
  };

  xresources.extraConfig = builtins.readFile ../../dotfiles/Xresources;
# read rofi config and replace DPI with dpi
  xdg.configFile."rofi/config.rasi".text = builtins.replaceStrings ["DPI" "WIDTH" "HEIGHT"] [DPI rofi_width rofi_height] (builtins.readFile ../../dotfiles/rofi);
  xdg.configFile."variety/variety.conf".text = builtins.readFile ../../dotfiles/variety.conf;
  xdg.configFile."variety/pluginconfig/quotes/quotes.txt".text = builtins.readFile ../../dotfiles/quotes.txt;
  home.file."scripts/set_wallpaper" = {
    text = builtins.readFile scripts/set_wallpaper;
    executable = true;
  };
  home.pointerCursor = {
    name = "Vanilla-DMZ";
    package = pkgs.vanilla-dmz;
    size = 32;
    gtk.enable = true;
    x11.enable = true;
  };
}
