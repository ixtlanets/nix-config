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
    home-manager.inputs.nixpkgs.follows = "nixpkgs-unstable";

    # NUR
    nur.url = "github:nix-community/NUR";

    hardware.url = "github:nixos/nixos-hardware/master";

    darwin.url = "github:lnl7/nix-darwin";
    darwin.inputs.nixpkgs.follows = "nixpkgs";

    niknvim.url = "github:ixtlanets/nixnvim";
    niknvim.inputs.nixpkgs.follows = "nixpkgs";

    catppuccin.url = "github:catppuccin/nix";


    # Shameless plug: looking for a way to nixify your themes and make
    # everything match nicely? Try nix-colors!
    # nix-colors.url = "github:misterio77/nix-colors";
  };

  outputs = { self, nixpkgs, home-manager, hardware, nur, darwin, niknvim, catppuccin, ... }@inputs:
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
            specialArgs = { inherit inputs outputs dpi; };
            modules = [
              catppuccin.nixosModules.catppuccin
              nur.nixosModules.nur
              ./hosts/x1carbon/nixos/configuration.nix
              hardware.nixosModules.lenovo-thinkpad-x1-6th-gen
              hardware.nixosModules.common-cpu-intel
              hardware.nixosModules.common-pc-laptop
              hardware.nixosModules.common-pc-laptop-ssd
              home-manager.nixosModules.home-manager
              {
                home-manager = {
                  useUserPackages = true;
                  extraSpecialArgs = { inherit outputs nur niknvim dpi; };
                  users.nik.imports = [ 
                    nur.nixosModules.nur
                    catppuccin.homeManagerModules.catppuccin
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
              nur.nixosModules.nur
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
                  extraSpecialArgs = { inherit outputs nur niknvim dpi; };
                  users.nik.imports = [
                    nur.nixosModules.nur
                    catppuccin.homeManagerModules.catppuccin
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
              nur.nixosModules.nur
              ./hosts/x13/nixos/configuration.nix
              ./modules/nixos/laptop.nix
              hardware.nixosModules.common-cpu-amd
              hardware.nixosModules.common-cpu-amd-pstate
              hardware.nixosModules.common-gpu-amd
              hardware.nixosModules.common-pc-laptop
              hardware.nixosModules.common-pc-laptop-ssd
              home-manager.nixosModules.home-manager
              {
                home-manager = {
                  useUserPackages = true;
                  backupFileExtension = "backup";
                  extraSpecialArgs = { inherit outputs nur niknvim dpi; };
                  users.nik.imports = [ 
                    nur.nixosModules.nur
                    catppuccin.homeManagerModules.catppuccin
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
              nur.nixosModules.nur
              ./hosts/um960pro/nixos/configuration.nix
              ./modules/nixos/laptop.nix
              hardware.nixosModules.common-cpu-amd
              hardware.nixosModules.common-cpu-amd-pstate
              hardware.nixosModules.common-gpu-amd
              hardware.nixosModules.common-pc-laptop
              hardware.nixosModules.common-pc-laptop-ssd
              home-manager.nixosModules.home-manager
              {
                home-manager = {
                  useUserPackages = true;
                  extraSpecialArgs = { inherit outputs nur niknvim dpi; };
                  users.nik.imports = [ 
                    nur.nixosModules.nur
                    catppuccin.homeManagerModules.catppuccin
                    ./hosts/um960pro/home-manager/home.nix
                  ];
                };
              }
            ];
          };


        zenbook =
          let
            dpi = 192;
          in
          nixpkgs.lib.nixosSystem {
            specialArgs = { inherit inputs outputs dpi; };
            modules = [
              catppuccin.nixosModules.catppuccin
              nur.nixosModules.nur
              ./hosts/zenbook/nixos/configuration.nix
              ./modules/nixos/laptop.nix
              hardware.nixosModules.common-cpu-intel
              hardware.nixosModules.common-gpu-nvidia
              {
                hardware.nvidia.open = false;
                hardware.nvidia.prime = {
                  intelBusId = "PCI:0:2:0";
                  nvidiaBusId = "PCI:1:0:0";
                };
              }
              hardware.nixosModules.common-pc-laptop
              hardware.nixosModules.common-pc-laptop-ssd
              home-manager.nixosModules.home-manager
              {
                home-manager = {
                  useUserPackages = true;
                  extraSpecialArgs = { inherit outputs nur niknvim dpi; };
                  users.nik.imports = [ 
                    nur.nixosModules.nur
                    catppuccin.homeManagerModules.catppuccin
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
              nur.nixosModules.nur
              ./hosts/matebook/nixos/configuration.nix
              hardware.nixosModules.common-cpu-intel
              hardware.nixosModules.common-gpu-intel
              hardware.nixosModules.common-pc-laptop
              hardware.nixosModules.common-pc-laptop-ssd
              home-manager.nixosModules.home-manager
              {
                home-manager = {
                  useUserPackages = true;
                  extraSpecialArgs = { inherit outputs nur niknvim dpi; };
                  users.nik.imports = [
                    nur.nixosModules.nur
                    catppuccin.homeManagerModules.catppuccin
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
                  extraSpecialArgs = { inherit outputs nur niknvim dpi; };
                  users.nik.imports = [
                    nur.nixosModules.nur
                    catppuccin.homeManagerModules.catppuccin
                    ./hosts/desktop/home-manager/home.nix
                  ];
                };
              }
            ];
          };


        vmmac =
          let
            dpi = 192;
          in
          nixpkgs.lib.nixosSystem {
            specialArgs = { inherit inputs outputs dpi; };
            modules = [
              catppuccin.nixosModules.catppuccin
              nur.nixosModules.nur
              # > Our main nixos configuration file <
              ./hosts/vmmac/nixos/configuration.nix
              home-manager.nixosModules.home-manager
              {
                home-manager = {
                  useUserPackages = true;
                  extraSpecialArgs = { inherit outputs nur niknvim dpi; };
                  users.nik.imports = [
                    nur.nixosModules.nur
                    catppuccin.homeManagerModules.catppuccin
                    ./hosts/vmmac/home-manager/home.nix
                  ];
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
          extraSpecialArgs = { inherit inputs outputs niknvim; };
          modules = [
            # > Our main home-manager configuration file <
            ./hosts/wsl/home-manager/home.nix
          ];
        };
      };
    };
}
