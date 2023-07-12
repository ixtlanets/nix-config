{
  description = "Your new nix config";

  inputs = {
    # Nixpkgs
    nixpkgs.url = "github:nixos/nixpkgs/nixpkgs-unstable";
    # You can access packages and modules from different nixpkgs revs
    # at the same time. Here's an working example:
    nixpkgs-unstable.url = "github:nixos/nixpkgs/nixos-unstable";
    # Also see the 'unstable-packages' overlay at 'overlays/default.nix'.

    # Home manager
    home-manager.url = "github:nix-community/home-manager/master";
    home-manager.inputs.nixpkgs.follows = "nixpkgs";

    # NUR
    nur.url = "github:nix-community/NUR";

    hardware.url = "github:nixos/nixos-hardware/master";

    darwin.url = "github:lnl7/nix-darwin";
    darwin.inputs.nixpkgs.follows = "nixpkgs";

    niknvim.url = "github:ixtlanets/nixnvim";
    niknvim.inputs.nixpkgs.follows = "nixpkgs";

    # Shameless plug: looking for a way to nixify your themes and make
    # everything match nicely? Try nix-colors!
    # nix-colors.url = "github:misterio77/nix-colors";
  };

  outputs = { self, nixpkgs, home-manager, hardware, nur, darwin, niknvim, ... }@inputs:
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
    rec {
      # Your custom packages
      # Acessible through 'nix build', 'nix shell', etc
      packages = forAllSystems (system:
        let pkgs = nixpkgs.legacyPackages.${system};
        in import ./pkgs { inherit pkgs; }
      );
      # Devshell for bootstrapping
      # Acessible through 'nix develop' or 'nix-shell' (legacy)
      devShells = forAllSystems (system:
        let pkgs = nixpkgs.legacyPackages.${system};
        in import ./shell.nix { inherit pkgs; }
      );

      # Your custom packages and modifications, exported as overlays
      overlays = import ./overlays { inherit inputs nur; };
      # Reusable nixos modules you might want to export
      # These are usually stuff you would upstream into nixpkgs
      nixosModules = import ./modules/nixos;
      # Reusable home-manager modules you might want to export
      # These are usually stuff you would upstream into home-manager
      homeManagerModules = import ./modules/home-manager;

      # NixOS configuration entrypoint
      # Available through 'nixos-rebuild --flake .#your-hostname'
      nixosConfigurations = {
        x1carbon = nixpkgs.lib.nixosSystem {
          specialArgs = { inherit inputs outputs; };
          modules = [
            nur.nixosModules.nur
            # > Our main nixos configuration file <
            ./hosts/x1carbon/nixos/configuration.nix
            hardware.nixosModules.lenovo-thinkpad-x1-6th-gen
            hardware.nixosModules.common-cpu-intel
            hardware.nixosModules.common-gpu-intel
            hardware.nixosModules.common-gpu-nvidia {
              hardware.nvidia.prime = {
                intelBusId = "PCI:0:2:0";
                nvidiaBusId = "PCI:11:0:0";
              };
            }
            hardware.nixosModules.common-pc-laptop
            hardware.nixosModules.common-pc-laptop-ssd
            home-manager.nixosModules.home-manager
            {
              home-manager = {
                useUserPackages = true;
                extraSpecialArgs = { inherit outputs nur niknvim; };
                users.nik.imports = [ ./hosts/x1carbon/home-manager/home.nix ];
              };
            }
          ];
        };
        x1extreme = nixpkgs.lib.nixosSystem {
          specialArgs = { inherit inputs outputs; };
          modules = [
            nur.nixosModules.nur
            # > Our main nixos configuration file <
            ./hosts/x1extreme/nixos/configuration.nix
            hardware.nixosModules.common-cpu-intel
            hardware.nixosModules.common-gpu-intel
            hardware.nixosModules.common-gpu-nvidia {
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
                extraSpecialArgs = { inherit outputs nur niknvim; };
                users.nik.imports = [ ./hosts/x1extreme/home-manager/home.nix ];
              };
            }
          ];
        };
        x13 = nixpkgs.lib.nixosSystem {
          specialArgs = { inherit inputs outputs; };
          modules = [
            nur.nixosModules.nur
            # > Our main nixos configuration file <
            ./hosts/x13/nixos/configuration.nix
            ./modules/nixos/laptop.nix
            hardware.nixosModules.common-cpu-amd
            hardware.nixosModules.common-cpu-amd-pstate
            hardware.nixosModules.common-gpu-amd
            hardware.nixosModules.common-gpu-nvidia-disable
            hardware.nixosModules.common-pc-laptop
            hardware.nixosModules.common-pc-laptop-ssd
            home-manager.nixosModules.home-manager
            {
              home-manager = {
                useUserPackages = true;
                extraSpecialArgs = { inherit outputs nur niknvim; };
                users.nik.imports = [ ./hosts/x13/home-manager/home.nix ];
              };
            }
          ];
        };

        matebook = nixpkgs.lib.nixosSystem {
          specialArgs = { inherit inputs outputs; };
          modules = [
            nur.nixosModules.nur
            # > Our main nixos configuration file <
            ./hosts/matebook/nixos/configuration.nix
            hardware.nixosModules.common-cpu-intel
            hardware.nixosModules.common-gpu-intel
            hardware.nixosModules.common-pc-laptop
            hardware.nixosModules.common-pc-laptop-ssd
            home-manager.nixosModules.home-manager
            {
              home-manager = {
                useUserPackages = true;
                extraSpecialArgs = { inherit outputs nur niknvim; };
                users.nik.imports = [ ./hosts/matebook/home-manager/home.nix ];
              };
            }
          ];
        };
      };
      darwinConfigurations.m1max = darwin.lib.darwinSystem {
        specialArgs = { inherit inputs outputs darwin; };
        system = "aarch64-darwin";
        pkgs = import nixpkgs { system = "aarch64-darwin"; config.allowUnfree = true; };
        modules = [
          nur.nixosModules.nur
          ./hosts/m1max/nixos/configuration.nix
          home-manager.darwinModules.home-manager
          {
            home-manager = {
              useUserPackages = true;
              extraSpecialArgs = { inherit outputs nur niknvim; };
              users.nik.imports = [ ./hosts/m1max/home-manager/home.nix ];
            };
          }
        ];
      };
      # Standalone home-manager configuration entrypoint
      # Available through 'home-manager --flake .#your-username@your-hostname'
      homeConfigurations = {
        "nik@wsl" = home-manager.lib.homeManagerConfiguration {
          pkgs = nixpkgs.legacyPackages.x86_64-linux; # Home-manager requires 'pkgs' instance
          extraSpecialArgs = { inherit inputs outputs niknvim; };
          modules = [
            # > Our main home-manager configuration file <
            ./hosts/wsl/home-manager/home.nix
          ];
        };
      };
    };
}
