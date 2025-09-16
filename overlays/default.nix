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
        version = "0.36.0";
        buildType = "simple";
        cargoSetupPostPatchHook = ":";
        nativeBuildInputs = [ prev.zstd ];
        src =
          if prev.stdenv.isLinux && prev.stdenv.isx86_64 then
            prev.fetchurl {
              url = "https://github.com/openai/codex/releases/download/rust-v${version}/codex-x86_64-unknown-linux-musl.zst";
              sha256 = "320062ab20916802006c820fee43063472313f26ae63bbeb52689e9fa420f129";
            }
          else if prev.stdenv.isLinux && prev.stdenv.isAarch64 then
            prev.fetchurl {
              url = "https://github.com/openai/codex/releases/download/rust-v${version}/codex-aarch64-unknown-linux-musl.zst";
              sha256 = "896b1a49bcec675d522a4f216e71a714cbe3de3661116ca5bb654a7e82a3a625";
            }
          else if prev.stdenv.isDarwin && prev.stdenv.isAarch64 then
            prev.fetchurl {
              url = "https://github.com/openai/codex/releases/download/rust-v${version}/codex-aarch64-apple-darwin.zst";
              sha256 = "31f480d145e985a25c069c60f14d9e0056c70e0566a13442e77dfa84d5da168f";
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
