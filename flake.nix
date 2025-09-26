{
  description = "Your new nix config";

  nixConfig = {
    extra-trusted-substituters = [ "https://cache.flox.dev" ];
    extra-trusted-public-keys = [ "flox-cache-public-1:7F4OyH7ZCnFhcze3fJdfyXYLQw/aV7GEed86nQ7IsOs=" ];
  };

  inputs = {
    # Nixpkgs
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
    # You can access packages and modules from different nixpkgs revs
    # at the same time. Here's an working example:
    nixpkgs-unstable.url = "github:nixos/nixpkgs/nixos-unstable";
    # Also see the 'unstable-packages' overlay at 'overlays/default.nix'.

    # Home manager
    home-manager.url = "github:nix-community/home-manager/master";
    home-manager.inputs.nixpkgs.follows = "nixpkgs-unstable";

    hardware.url = "github:nixos/nixos-hardware/master";

    darwin.url = "github:lnl7/nix-darwin";
    darwin.inputs.nixpkgs.follows = "nixpkgs";

    catppuccin.url = "github:catppuccin/nix";

    ghostty.url = "github:ghostty-org/ghostty";

    disko.url = "github:nix-community/disko/latest";
    disko.inputs.nixpkgs.follows = "nixpkgs";

    nixos-facter-modules.url = "github:numtide/nixos-facter-modules";

    hyprland.url = "github:hyprwm/Hyprland";

    plasma-manager = {
      url = "github:nix-community/plasma-manager";
      inputs.nixpkgs.follows = "nixpkgs";
      inputs.home-manager.follows = "home-manager";
    };

    flox.url = "github:flox/flox/v1.7.3";
  };

  outputs =
    {
      self,
      nixpkgs,
      home-manager,
      plasma-manager,
      hardware,
      darwin,
      catppuccin,
      ghostty,
      disko,
      ...
    }@inputs:
    let
      inherit (self) outputs;
      forAllSystems = nixpkgs.lib.genAttrs [
        "aarch64-linux"
        "i686-linux"
        "x86_64-linux"
        "aarch64-darwin"
        "x86_64-darwin"
      ];
    in
    {
      # Code formatter for `nix fmt`
      formatter = forAllSystems (system: nixpkgs.legacyPackages.${system}.nixfmt-rfc-style);

      # CI checks (formatting + linting) exposed as flake checks
      checks = forAllSystems (
        system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
        in
        {
          fmt =
            pkgs.runCommand "fmt-check"
              {
                nativeBuildInputs = [
                  pkgs.nixfmt-rfc-style
                  pkgs.findutils
                ];
              }
              ''
                set -eu
                files=$(find . -type f -name '*.nix' | tr '\n' ' ')
                if [ -n "''${files}" ]; then
                  nixfmt --check ''${files}
                fi
                mkdir -p "$out"
              '';
          statix = pkgs.runCommand "statix-check" { nativeBuildInputs = [ pkgs.statix ]; } ''
            set -eu
            # Advisory only; do not fail the build in checks
            statix check . || true
            mkdir -p "$out"
          '';
          deadnix = pkgs.runCommand "deadnix-check" { nativeBuildInputs = [ pkgs.deadnix ]; } ''
            set -eu
            # Advisory only; do not fail the build in checks
            deadnix --fail . || true
            mkdir -p "$out"
          '';
        }
      );

      # Your custom packages
      # Acessible through 'nix build', 'nix shell', etc
      packages = forAllSystems (
        system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
        in
        import ./pkgs { inherit pkgs; }
      );
      # Devshell for bootstrapping
      # Acessible through 'nix develop' or 'nix-shell' (legacy)
      devShells = forAllSystems (
        system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
        in
        import ./shell.nix { inherit pkgs; }
      );

      # Your custom packages and modifications, exported as overlays
      overlays = import ./overlays { inherit inputs; };
      # Reusable nixos modules you might want to export
      # These are usually stuff you would upstream into nixpkgs
      nixosModules = import ./modules/nixos;
      # Reusable home-manager modules you might want to export
      # These are usually stuff you would upstream into home-manager
      homeManagerModules = import ./modules/home-manager;

      # NixOS configuration entrypoint
      # Available through 'nixos-rebuild --flake .#your-hostname'
      nixosConfigurations = {
        x1carbon =
          let
            dpi = 144;
          in
          nixpkgs.lib.nixosSystem {
            specialArgs = {
              inherit
                inputs
                outputs
                dpi
                ghostty
                ;
            };
            modules = [
              catppuccin.nixosModules.catppuccin
              ./hosts/x1carbon/nixos/configuration.nix
              hardware.nixosModules.lenovo-thinkpad-x1-6th-gen
              hardware.nixosModules.common-cpu-intel
              hardware.nixosModules.common-pc-laptop
              hardware.nixosModules.common-pc-laptop-ssd
              home-manager.nixosModules.home-manager
              {
                home-manager = {
                  useUserPackages = true;
                  extraSpecialArgs = {
                    inherit
                      inputs
                      outputs
                      dpi
                      ghostty
                      ;
                  };
                  sharedModules = [ plasma-manager.homeManagerModules.plasma-manager ];
                  users.nik.imports = [
                    catppuccin.homeModules.catppuccin
                    ./hosts/x1carbon/home-manager/home.nix
                  ];
                };
              }
            ];
          };
        x1extreme =
          let
            dpi = 144;
          in
          nixpkgs.lib.nixosSystem {
            specialArgs = { inherit inputs outputs dpi; };
            modules = [
              catppuccin.nixosModules.catppuccin
              ./hosts/x1extreme/nixos/configuration.nix
              ./modules/nixos/laptop.nix
              hardware.nixosModules.common-cpu-intel
              hardware.nixosModules.common-gpu-nvidia
              {
                hardware.nvidia.prime = {
                  intelBusId = "PCI:0:2:0";
                  nvidiaBusId = "PCI:9:0:0";
                };
              }
              hardware.nixosModules.common-pc-laptop
              hardware.nixosModules.common-pc-laptop-ssd
              home-manager.nixosModules.home-manager
              {
                home-manager = {
                  useUserPackages = true;
                  extraSpecialArgs = {
                    inherit
                      inputs
                      outputs
                      dpi
                      ghostty
                      ;
                  };
                  sharedModules = [ plasma-manager.homeManagerModules.plasma-manager ];
                  users.nik.imports = [
                    catppuccin.homeModules.catppuccin
                    ./hosts/x1extreme/home-manager/home.nix
                  ];
                };
              }
            ];
          };
        x13 =
          let
            dpi = 144;
          in
          nixpkgs.lib.nixosSystem {
            specialArgs = { inherit inputs outputs dpi; };
            modules = [
              catppuccin.nixosModules.catppuccin
              ./hosts/x13/nixos/configuration.nix
              disko.nixosModules.disko
              ./hosts/x13/nixos/disko-config.nix
              hardware.nixosModules.common-cpu-amd
              hardware.nixosModules.common-cpu-amd-pstate
              hardware.nixosModules.common-gpu-amd
              hardware.nixosModules.common-gpu-nvidia
              {
                hardware.nvidia = {
                  open = true;
                  prime = {
                    amdgpuBusId = "PCI:56:0:0";
                    nvidiaBusId = "PCI:10:0:0";
                  };
                };
              }
              hardware.nixosModules.common-pc-laptop
              hardware.nixosModules.common-pc-laptop-ssd
              home-manager.nixosModules.home-manager
              {
                home-manager = {
                  useUserPackages = true;
                  backupFileExtension = "backup";
                  extraSpecialArgs = {
                    inherit
                      inputs
                      outputs
                      dpi
                      ghostty
                      ;
                  };
                  sharedModules = [ plasma-manager.homeManagerModules.plasma-manager ];
                  users.nik.imports = [
                    catppuccin.homeModules.catppuccin
                    ./hosts/x13/home-manager/home.nix
                  ];
                };
              }
            ];
          };
        um960pro =
          let
            dpi = 144;
          in
          nixpkgs.lib.nixosSystem {
            specialArgs = { inherit inputs outputs dpi; };
            modules = [
              catppuccin.nixosModules.catppuccin
              ./hosts/um960pro/nixos/configuration.nix
              ./modules/nixos/laptop.nix
              disko.nixosModules.disko
              ./hosts/um960pro/nixos/disko-config.nix
              hardware.nixosModules.common-cpu-amd
              hardware.nixosModules.common-cpu-amd-pstate
              hardware.nixosModules.common-gpu-amd
              hardware.nixosModules.common-gpu-nvidia
              hardware.nixosModules.common-pc-laptop
              hardware.nixosModules.common-pc-laptop-ssd
              home-manager.nixosModules.home-manager
              {
                home-manager = {
                  useUserPackages = true;
                  extraSpecialArgs = {
                    inherit
                      inputs
                      outputs
                      dpi
                      ghostty
                      ;
                  };
                  sharedModules = [ plasma-manager.homeManagerModules.plasma-manager ];
                  users.nik.imports = [
                    catppuccin.homeModules.catppuccin
                    ./hosts/um960pro/home-manager/home.nix
                  ];
                };
              }
            ];
          };

        zenbook =
          let
            dpi = 144;
          in
          nixpkgs.lib.nixosSystem {
            specialArgs = { inherit inputs outputs dpi; };
            modules = [
              catppuccin.nixosModules.catppuccin
              ./hosts/zenbook/nixos/configuration.nix
              ./modules/nixos/laptop.nix
              disko.nixosModules.disko
              ./hosts/zenbook/nixos/disko-config.nix
              hardware.nixosModules.common-cpu-intel
              hardware.nixosModules.common-gpu-nvidia
              {
                hardware.nvidia = {
                  open = true;
                  prime = {
                    intelBusId = "PCI:0:2:0";
                    nvidiaBusId = "PCI:1:0:0";
                  };
                };
              }
              hardware.nixosModules.common-pc-laptop
              hardware.nixosModules.common-pc-laptop-ssd
              home-manager.nixosModules.home-manager
              {
                home-manager = {
                  useUserPackages = true;
                  extraSpecialArgs = {
                    inherit
                      inputs
                      outputs
                      dpi
                      ghostty
                      ;
                  };
                  sharedModules = [ plasma-manager.homeManagerModules.plasma-manager ];
                  users.nik.imports = [
                    catppuccin.homeModules.catppuccin
                    ./hosts/zenbook/home-manager/home.nix
                  ];
                };
              }
            ];
          };

        matebook =
          let
            dpi = 192;
          in
          nixpkgs.lib.nixosSystem {
            specialArgs = { inherit inputs outputs dpi; };
            modules = [
              catppuccin.nixosModules.catppuccin
              ./hosts/matebook/nixos/configuration.nix
              ./modules/nixos/laptop.nix
              disko.nixosModules.disko
              ./hosts/matebook/nixos/disko-config.nix
              hardware.nixosModules.common-cpu-intel
              hardware.nixosModules.common-gpu-intel
              hardware.nixosModules.common-pc-laptop
              hardware.nixosModules.common-pc-laptop-ssd
              home-manager.nixosModules.home-manager
              {
                home-manager = {
                  useUserPackages = true;
                  extraSpecialArgs = {
                    inherit
                      inputs
                      outputs
                      dpi
                      ghostty
                      ;
                  };
                  sharedModules = [ plasma-manager.homeManagerModules.plasma-manager ];
                  users.nik.imports = [
                    catppuccin.homeModules.catppuccin
                    ./hosts/matebook/home-manager/home.nix
                  ];
                };
              }
            ];
          };

        desktop =
          let
            dpi = 192;
          in
          nixpkgs.lib.nixosSystem {
            specialArgs = { inherit inputs outputs dpi; };
            modules = [
              catppuccin.nixosModules.catppuccin
              ./hosts/desktop/nixos/configuration.nix
              hardware.nixosModules.common-cpu-amd
              hardware.nixosModules.common-cpu-amd-pstate
              hardware.nixosModules.common-pc-ssd
              home-manager.nixosModules.home-manager
              {
                home-manager = {
                  useUserPackages = true;
                  extraSpecialArgs = {
                    inherit
                      inputs
                      outputs
                      dpi
                      ghostty
                      ;
                  };
                  sharedModules = [ plasma-manager.homeManagerModules.plasma-manager ];
                  users.nik.imports = [
                    catppuccin.homeModules.catppuccin
                    ./hosts/desktop/home-manager/home.nix
                  ];
                };
              }
            ];
          };

      };
      darwinConfigurations.m1max = darwin.lib.darwinSystem {
        specialArgs = { inherit inputs outputs darwin; };
        system = "aarch64-darwin";
        pkgs = import nixpkgs {
          system = "aarch64-darwin";
          config.allowUnfree = true;
        };
        modules = [
          ./hosts/m1max/nixos/configuration.nix
          home-manager.darwinModules.home-manager
          {
            home-manager = {
              useUserPackages = true;
              extraSpecialArgs = { inherit inputs outputs; };
              users.nik.imports = [
                catppuccin.homeModules.catppuccin
                ./hosts/m1max/home-manager/home.nix
              ];
            };
          }
        ];
      };
      # Standalone home-manager configuration entrypoint
      # enable flakes and nix command first.
      # to do so, you need to put to the /etc/nix/nix.conf
      # experimental-features = nix-command flakes
      # you also need to install home-manager standalone
      # nix-channel --add https://github.com/nix-community/home-manager/archive/master.tar.gz home-manager
      # nix-channel --update
      # nix-shell '<home-manager>' -A install
      # after that you can activate configuration
      # available through 'home-manager --flake .#nik@wsl switch'
      homeConfigurations = {
        "nik@wsl" = home-manager.lib.homeManagerConfiguration {
          pkgs = nixpkgs.legacyPackages.x86_64-linux; # Home-manager requires 'pkgs' instance
          extraSpecialArgs = { inherit inputs outputs; };
          modules = [
            catppuccin.homeModules.catppuccin
            # > Our main home-manager configuration file <
            ./hosts/wsl/home-manager/home.nix
          ];
        };
        "nik@ubuntu" = home-manager.lib.homeManagerConfiguration {
          pkgs = nixpkgs.legacyPackages.x86_64-linux; # Home-manager requires 'pkgs' instance
          extraSpecialArgs = {
            inherit
              inputs
              outputs
              ghostty
              ;
          };
          modules = [
            # > Our main home-manager configuration file <
            ./hosts/ubuntu/home-manager/home.nix
          ];
        };
      };
    };
}
