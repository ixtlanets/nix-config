{ config, pkgs, ... }:

{
  # Bootloader.
  boot.loader.systemd-boot.enable = true;
  boot.loader.systemd-boot.configurationLimit = 8;
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
  
  # Services

  services = {
    xserver = {
      enable = true;
      windowManager = {
        i3.enable = true;
      };
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
  xdg.portal.extraPortals = [ pkgs.xdg-desktop-portal-gtk ];

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

  # Define a user account. Don't forget to set a password with ‘passwd’.
  users.users.nik = {
    isNormalUser = true;
    description = "Sergey Nikulin";
    extraGroups = [ "networkmanager" "wheel" "video" ];
    shell = pkgs.zsh;
  };

  # Allow unfree packages
  nixpkgs.config.allowUnfree = true;

  # List packages installed in system profile. To search, run:
  # $ nix search wget
  environment.systemPackages = with pkgs; [
    zerotierone
    killall
    #  vim # Do not forget to add an editor to edit configuration.nix! The Nano editor is also installed by default.
    #  wget
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

  # Enable TLP
  services.power-profiles-daemon.enable = false;
  services.tlp.enable = true;
}
