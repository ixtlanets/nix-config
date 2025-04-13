{
  inputs,
  pkgs,
  lib,
  ...
}:
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

  services = {
    desktopManager.plasma6.enable = true;
    displayManager = {
      sddm = {
        enable = true;
        wayland.enable = true;
        settings = {
          Theme = {
            CursorTheme = "Bibata-Modern-Ice";
          };
        };
      };
    };
    xserver = {
      enable = true;
    };
  };

  # Services
  services = {
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

  services.fwupd.enable = true;
  services.dbus.enable = true;
  xdg.portal.extraPortals = with pkgs; [ xdg-desktop-portal-gtk ];

  # Enable CUPS to print documents.
  services.printing.enable = true;

  # Enable sound with pipewire.
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
    zerotierone
    killall
    jq
    unzip
    gum
    podman-compose
    vpn-script
    networkmanager-l2tp
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
    # Ebable virtualbox
    virtualbox.host = {
      enable = true;
      enableExtensionPack = true;
      enableKvm = true;
      addNetworkInterface = false;
    };
    libvirtd = {
      enable = true;
      qemu = {
        package = pkgs.qemu_kvm;
        runAsRoot = true;
        swtpm.enable = true;
        ovmf = {
          enable = true;
          packages = [
            (pkgs.OVMF.override {
              secureBoot = true;
              tpmSupport = true;
            }).fd
          ];
        };
      };
    };
    docker.enable = true;
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
