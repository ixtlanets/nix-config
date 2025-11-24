{
  inputs,
  pkgs,
  lib,
  ...
}:
let
  floxPkg = inputs.flox.packages.${pkgs.system}.default;
  vpn-script = pkgs.writeShellScriptBin "vpn" ''
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

  power-profile-script = pkgs.writeShellScriptBin "power-profile" ''
    # get current active profile
    CURRENT_PROFILE=$(powerprofilesctl list | grep "^\*" | sed 's/^\* \([^:]*\):.*/\1/')

    # get all available profiles
    AVAILABLE_PROFILES=$(powerprofilesctl list | grep ":$" | sed 's/^[* ]*\([^:]*\):.*/\1/')

    # let user select profile with gum
    SELECTED_PROFILE=$(echo "$AVAILABLE_PROFILES" | gum choose --selected "$CURRENT_PROFILE" --header "Select power profile")

    # apply selected profile
    powerprofilesctl set "$SELECTED_PROFILE"
  '';
in
{
  nix.settings.experimental-features = [
    "nix-command"
    "flakes"
  ];
  nix.settings.trusted-users = [
    "root"
    "nik"
  ];
  nix.settings.substituters = [
    "https://cache.nixos.org"
    "https://devenv.cachix.org"
    "https://cache.flox.dev"
  ];
  nix.settings.trusted-substituters = [ "https://cache.flox.dev" ];
  nix.settings.trusted-public-keys = [
    "cache.nixos.org-1:6NCHdD59X431o0gWypbMrAURkbJ16ZPMQFGspcDShjY="
    "devenv.cachix.org-1:w1cLUi8dv3hnoSPGAuibQv+f9TZtWKshxzYfXc0fJyQ="
    "flox-cache-public-1:7F4OyH7ZCnFhcze3fJdfyXYLQw/aV7GEed86nQ7IsOs="
  ];
  nix.nixPath = [ "nixpkgs=${inputs.nixpkgs}" ];

  # Bootloader.
  boot.loader.grub.enable = true;
  boot.loader.grub.configurationLimit = 8;
  boot.loader.grub.useOSProber = true;
  boot.loader.grub.efiSupport = true;
  boot.loader.grub.device = "nodev";
  boot.loader.efi.canTouchEfiVariables = true;
  boot.loader.efi.efiSysMountPoint = "/boot/efi";

  # enable power managment
  powerManagement.enable = true;

  # Use latest kernel
  boot.kernelPackages = pkgs.linuxPackages_zen;

  # Enable networking
  networking.networkmanager.enable = true;

  # disable rpfilter, since it'll be blocking Wireguard traffic
  networking.firewall.checkReversePath = lib.mkForce false;

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
    LC_TIME = "en_GB.UTF-8";
  };
  nixpkgs.config.joypixels.acceptLicense = true;

  fonts = {
    packages = with pkgs; [
      cascadia-code
      dejavu_fonts
      emacs-all-the-icons-fonts
      joypixels
      fira-code
      fira-mono
      font-awesome

      noto-fonts-color-emoji
      roboto
      source-code-pro
      source-sans-pro
      source-serif-pro
      twemoji-color-font
      nerd-fonts.jetbrains-mono
      nerd-fonts.fantasque-sans-mono
      nerd-fonts.iosevka
      nerd-fonts.victor-mono
    ];
    fontconfig = {
      hinting.autohint = true;
      antialias = true;
      allowBitmaps = true;
      useEmbeddedBitmaps = true;
      defaultFonts = {
        monospace = [ "JetBrains Mono" ];
        sansSerif = [ "Roboto" ];
        serif = [ "Source Serif Pro" ];
      };
    };
  };

  programs = {
    zsh.enable = true;
    dconf.enable = true;
    nix-ld = {
      # required fro vscode-server
      enable = true;
      libraries = with pkgs; [
        glibc
      ];
    };
  };

  # Services
  services = {
    tailscale = {
      enable = true;
      useRoutingFeatures = "both";
    };
    fwupd.enable = true;
    dbus.enable = true;
    pipewire = {
      enable = true;
      alsa.enable = true;
      alsa.support32Bit = true;
      pulse.enable = true;
    };
    printing.enable = true;
  };
  xdg.mime = {
    enable = true;
    defaultApplications = {
      "application/pdf" = "zathura.desktop";
      "image/png" = "nsxiv.desktop";
      "image/jpeg" = "nsxiv.desktop";
      "image/gif " = "nsxiv.desktop";
      "image/webp" = "nsxiv.desktop";
      "image/bmp " = "nsxiv.desktop";
      "image/tiff" = "nsxiv.desktop";
      "text/html" = "brave.desktop";
      "x-scheme-handler/http" = "brave.desktop";
      "x-scheme-handler/https" = "brave.desktop";
      "video/mp4" = "mpv.desktop";
      "video/x-msvideo" = "mpv.desktop";
      "video/x-matroska" = "mpv.desktop";
      "video/x-flv" = "mpv.desktop";
      "video/x-ms-wmv" = "mpv.desktop";
      "video/mpeg" = "mpv.desktop";
      "video/ogg" = "mpv.desktop";
      "video/webm" = "mpv.desktop";
      "video/quicktime" = "mpv.desktop";
      "video/3gpp" = "mpv.desktop";
      "video/3gpp2" = "mpv.desktop";
      "video/x-ms-asf" = "mpv.desktop";
      "video/x-ogm+ogg" = "mpv.desktop";
      "video/x-theora+ogg" = "mpv.desktop";
      "application/ogg" = "mpv.desktop";
    };
  };

  # Enable sound with pipewire.
  services.pulseaudio.enable = false;

  hardware.bluetooth.enable = true; # enables support for Bluetooth
  hardware.bluetooth.powerOnBoot = true; # powers up the default Bluetooth controller on boot

  # Define a user account. Don't forget to set a password with ‘passwd’.
  users.users.nik = {
    isNormalUser = true;
    description = "Sergey Nikulin";
    extraGroups = [
      "networkmanager"
      "wheel"
      "video"
      "docker"
      "vboxusers"
      "libvirtd"
    ];
    shell = pkgs.zsh;
    openssh.authorizedKeys.keys = [
      "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQC35qP3UeDJNWzN1ux5FY6Mnsj7KLAmRRt254vjz1Ry5SNwdLE1VhVPVnmIufyKWK5/z6g8NiPvFxXzAyKCitpSS6ahYQjKCXS9b5P3C+FPLcwcy1Ge54Fdu1qGzTeElbIm86+MSA1aQgwbzVfHQYl/TLBk7QVTJ5SdQgdBe7w3tt4hkQMhsqTue6FKF0sTF3xMcKf8B/CSmYHgFiVZsiqg+hb8sYBogIc5vsFlNfxg14UMriGh6/wOvNvZIn7IwgGB2tKGCEtS4p9PL7Vd+LHYUgwta2a/KXgH3xQEuCKDwGPJWpE4kkbSr1SNdQuGZP3Ry9Ta5TMIEgQ8n0mAD9lR nik@msi-ubuntu"
      "ssh-rsa AAAAB3NzaC1yc2EAAAABJQAAAQEAtj2ANdOntRVwWXdMm9FWu2fwDZNH2uEJH+vI37AfPwlmITtxBsOCM9/CYK/wkQa2elfkgkRYqvww0IlwCzI9/88t9YX7CWZU7z/P8ISufNL5VUOfiu15712CJjieauLOzTbAvyFvPhhqTkOpk/Fe1Mi1kFVaBlLqZjHsgokViACOmi+P06XFj0Bl//zAYvqC7mFSRGKDjmicW6vnUxShH6r4QQJv9J2z4KrDHs1ZWUOyWabqaVR4qD/vuGg2kYF/J1YaLKnNQGVNVtSmsaDbwTmev5dPKpZIxgRzl+MyaHDaCCxnzp6dHnjnlP8cfFW55t3Aea5JQCW8vtRrrwKExQ=="
      "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQCgv72CRql2CHmORIPFv4bgLNbdWQbgKbb4VOHqIBnoWddXi1PfoDuhesKrLwr+tvuNcOVzdPo69nh6NhXMsOW3it7FHeEsZ9ADH8W6PiZyEItDvTtrI6j6776ZGsn+pJ0Mj+qP4fZrSkmdd13tiKiigkX5Sif04vlTDGyQiL8zVOiigEO0UIUfTlw45KrE8/iqVnCoVzcaVqQ7QjNUOhGeiKihoIcyco++XiS1Qs2nw8oSvXphQ6KGjGMq1adGl7+4HEYJgkjN0dQqfkZzZtY5TfwKOFGKofj/TRP+pntBbl8RhtBwPpI7lbEQljv715PwYgAHVYhWuOlBQhskGz5L nik@ubuntu-server"
    ];
    initialHashedPassword = "$y$j9T$BqTWVOGlz9SA/HLpKXb0E0$HAp9.7RoQMgTLYhF.nScFDnQKJIDNRGi/Z1ihJX.FP/";
  };

  # Allow unfree packages
  nixpkgs.config.allowUnfree = true;

  # List packages installed in system profile. To search, run:
  # $ nix search wget
  environment.systemPackages = with pkgs; [
    floxPkg
    killall
    jq
    fzf
    unzip
    gum
    vpn-script
    power-profile-script
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
    docker = {
      enable = true;
      extraPackages = with pkgs; [ docker-buildx ];
    };
    libvirtd = {
      enable = true;
      qemu = {
        swtpm.enable = true;
      };
    };
    spiceUSBRedirection.enable = true;
  };
  programs = {
    _1password-gui = {
      enable = true;
      polkitPolicyOwners = [ "nik" ];
    };
    virt-manager.enable = true;
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
          {
            command = "${pkgs.tailscale}/bin/tailscale";
            options = [
              "SETENV"
              "NOPASSWD"
            ];
          }
        ];
      }
    ];
  };

}
