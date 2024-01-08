{ config, pkgs, ... }:
let
vpn-script = pkgs.writeShellScriptBin "vpn" ''
#!/usr/bin/env nix-shell
# gen dns suffix
DNS_SUFFIX=$(tailscale status --json | jq '.MagicDNSSuffix' | sed 's/"//g')

# get list of available exit nodes
EXIT_NODES=$(tailscale status --json | jq '.Peer[] | select(.ExitNodeOption==true) | select(.Online==true) | .DNSName' | sed "s/\.$DNS_SUFFIX\.//g" | sed 's/"//g')



# add 'None' to the list none option
EXIT_NODES+="\nNone"
EXIT_NODES=$(echo -e "$EXIT_NODES")

SELECTED=$(tailscale status --json | jq '.Peer[] | select(.ExitNode==true) | .DNSName' | sed "s/\.$DNS_SUFFIX\.//g" | sed 's/"//g')

# if SELECTED is empty, put None there
if [[ -z "$SELECTED" ]]; then
  SELECTED="None"
fi

#let user select exit node with gum
EXIT_NODE=$(gum choose --selected $SELECTED $EXIT_NODES)
if [[ "$EXIT_NODE" == "None" ]]; then
  sudo tailscale up --exit-node "" --exit-node-allow-lan-access=false
else
  sudo tailscale up --exit-node $EXIT_NODE --exit-node-allow-lan-access=true
fi

'';
in {
  nix.settings.experimental-features = [ "nix-command" "flakes" ];
  nix.settings.trusted-users = [ "root" "nik" ];

  # Bootloader.
  boot.loader.grub.enable = true;
  boot.loader.grub.configurationLimit = 8;
  boot.loader.grub.useOSProber = true;
  boot.loader.grub.efiSupport = true;
  boot.loader.grub.device = "nodev";
  boot.loader.efi.canTouchEfiVariables = true;
  boot.loader.efi.efiSysMountPoint = "/boot/efi";

  # Use latest kernel
  boot.kernelPackages = pkgs.linuxPackages_latest;

  # Enable networking
  networking.networkmanager.enable = true;

  # Set your time zone.
  time.timeZone = "Europe/Moscow";

  # Select internationalisation properties.
  i18n.defaultLocale = "en_US.UTF-8";

  i18n.extraLocaleSettings = {
    LC_ADDRESS = "ru_RU.UTF-8";
    LC_IDENTIFICATION = "ru_RU.UTF-8";
    LC_MEASUREMENT = "ru_RU.UTF-8";
    LC_MONETARY = "ru_RU.UTF-8";
    LC_NAME = "ru_RU.UTF-8";
    LC_NUMERIC = "ru_RU.UTF-8";
    LC_PAPER = "ru_RU.UTF-8";
    LC_TELEPHONE = "ru_RU.UTF-8";
    LC_TIME = "ru_RU.UTF-8";
  };

  programs = {
    zsh.enable = true;
    dconf.enable = true;
  };
  
  # required for  gnome systray
  services.udev.packages = with pkgs; [ gnome.gnome-settings-daemon ];
 
  # Services
  services = {
    xserver = {
      enable = true;
      displayManager = {
        gdm.enable = true;
        sessionCommands = ''
          ${pkgs.xorg.xset}/bin/xset r rate 250 30
        '';
      };
      windowManager = {
        i3.enable = true;
      };
      desktopManager.gnome.enable = true;
      libinput = {
        enable = true;
        mouse.middleEmulation = false;
        touchpad = {
          tapping = true;
          scrollMethod = "twofinger";
          naturalScrolling = true;                # The correct way of scrolling
          accelProfile = "adaptive";              # Speed settings
          #accelSpeed = "-0.5";
          disableWhileTyping = true;
        };
      };

      layout = "us,ru";
      xkbOptions = "grp:win_space_toggle";
    };
    tailscale = {
      enable = true;
      useRoutingFeatures = "both";
    };
    zerotierone = {
      enable = true;
      joinNetworks = [
        "88503383901a34c1"
      ];
    };
  };


  services.dbus.enable = true;
  xdg.portal.enable = true;
  xdg.portal.wlr.enable = true;
  # xdg.portal.extraPortals = [ xdg-desktop-portal-hyprland ];

  # Enable CUPS to print documents.
  services.printing.enable = true;

  # Enable sound with pipewire.
  sound.enable = true;
  hardware = {
    pulseaudio.enable = false;
  };
  security.rtkit.enable = true;
  security.polkit.enable = true;
  services.pipewire = {
    enable = true;
    alsa.enable = true;
    alsa.support32Bit = true;
    pulse.enable = true;
  };
  services.blueman.enable = true;

  # Define a user account. Don't forget to set a password with ‘passwd’.
  users.users.nik = {
    isNormalUser = true;
    description = "Sergey Nikulin";
    extraGroups = [ "networkmanager" "wheel" "video" "docker" ];
    shell = pkgs.zsh;
  };

  # Allow unfree packages
  nixpkgs.config.allowUnfree = true;

  # List packages installed in system profile. To search, run:
  # $ nix search wget
  environment.systemPackages = with pkgs; [
    zerotierone
    killall
    jq
    gum
    podman-compose
    vpn-script
    xdg-desktop-portal-hyprland
  ];


  # Some programs need SUID wrappers, can be configured further or are
  # started in user sessions.
  programs.mtr.enable = true;
  programs.gnupg.agent = {
    enable = true;
    enableSSHSupport = true;
  };
  programs.light.enable = true;

  # List services that you want to enable:

  # Enable the OpenSSH daemon.
  services.openssh.enable = true;

  # Docker

  # virtualisation.docker.enable = true;
  
  # Podman
  

  virtualisation = {
    podman = {
      enable = true;

      # Create a `docker` alias for podman, to use it as a drop-in replacement
      dockerCompat = true;

      # Required for containers under podman-compose to be able to talk to each other.
      defaultNetwork.settings.dns_enabled = true;
    };
  };


  services.power-profiles-daemon.enable = true;

  # Security options
  security.sudo = {
    enable = true;
    execWheelOnly = true;
    extraRules = [
      {
        groups = [ "wheel" ];
        commands = [
          { command = "${pkgs.tailscale}/bin/tailscale"; options = [ "SETENV" "NOPASSWD" ]; }
        ];
      }
    ];
  };
}
