# This file defines overlays
{ inputs, ... }:
{
  # This one brings our custom packages from the 'pkgs' directory
  additions = final: _prev: import ../pkgs { pkgs = final; };

  # This one contains whatever you want to overlay
  # You can change versions, add patches, set compilation flags, anything really.
  # https://nixos.wiki/wiki/Overlays
  modifications = final: prev: {
     tawm = inputs.tawm.packages.${prev.system}.default;
     codex = prev.codex.overrideAttrs (old: rec {
       version = "0.34.0";
       buildType = "simple";
       cargoSetupPostPatchHook = ":";
       nativeBuildInputs = [ prev.zstd ];
       src =
         if prev.stdenv.isLinux && prev.stdenv.isx86_64 then
           prev.fetchurl {
             url = "https://github.com/openai/codex/releases/download/rust-v${version}/codex-x86_64-unknown-linux-musl.zst";
             sha256 = "1r72wl2agv60zbsavlw2d3cljyf3x820kzmafp2ml7fdh7nnd023";
           }
         else if prev.stdenv.isLinux && prev.stdenv.isAarch64 then
           prev.fetchurl {
             url = "https://github.com/openai/codex/releases/download/rust-v${version}/codex-aarch64-unknown-linux-musl.zst";
             sha256 = "0kna13hvcnnxzlbc1h08r55qmrc1spd55v1vz456fxirajx1p6mi";
           }
         else if prev.stdenv.isDarwin && prev.stdenv.isAarch64 then
           prev.fetchurl {
             url = "https://github.com/openai/codex/releases/download/rust-v${version}/codex-aarch64-apple-darwin.zst";
             sha256 = "0sc0hjcy5zvc2f6dshykx61rksii9fi48fkcwgdgfrdm6zx51c86";
           }
         else throw "Unsupported system for codex";
       dontUnpack = true;
       installPhase = "mkdir -p $out/bin && zstd -d $src -o $out/bin/codex && chmod +x $out/bin/codex";
     });
     # example = prev.example.overrideAttrs (oldAttrs: rec {
     # ...
     # });
   };

  # When applied, the unstable nixpkgs set (declared in the flake inputs) will
  # be accessible through 'pkgs.unstable'
  unstable-packages = final: _prev: {
    unstable = import inputs.nixpkgs-unstable {
      system = final.system;
      config.allowUnfree = true;
    };
  };

}
