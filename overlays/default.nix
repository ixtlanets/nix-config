# This file defines overlays
{ inputs, ... }:
{
  # This one brings our custom packages from the 'pkgs' directory
  additions = final: prev: {
    opencode = final.callPackage ../pkgs/opencode.nix { };
    marker-pdf = final.callPackage ../pkgs/marker-pdf.nix { };
    google-genai = final.callPackage ../pkgs/google-genai.nix { };
    pdftext = final.callPackage ../pkgs/pdftext.nix { };
    surya-ocr = final.callPackage ../pkgs/surya-ocr.nix { };
    codebuddy-code = final.callPackage ../pkgs/codebuddy-code.nix { };
  };

  # This one contains whatever you want to overlay
  # You can change versions, add patches, set compilation flags, anything really.
  # https://nixos.wiki/wiki/Overlays
  modifications = final: prev: {
     tawm = inputs.tawm.packages.${prev.system}.default;
      codex = prev.codex.overrideAttrs (old: rec {
        version = "0.39.0";
        buildType = "simple";
        cargoSetupPostPatchHook = ":";
        nativeBuildInputs = [ prev.zstd ];
        src =
          if prev.stdenv.isLinux && prev.stdenv.isx86_64 then
            prev.fetchurl {
              url = "https://github.com/openai/codex/releases/download/rust-v${version}/codex-x86_64-unknown-linux-musl.zst";
              sha256 = "272f58f9b2d6db60e83277db0d4b0c99eb5d5999e55124bc9cac8c72f7846d05";
            }
          else if prev.stdenv.isLinux && prev.stdenv.isAarch64 then
            prev.fetchurl {
              url = "https://github.com/openai/codex/releases/download/rust-v${version}/codex-aarch64-unknown-linux-musl.zst";
              sha256 = "1a37b9b4ea436d463f78922dd0dbaf05f44a1fece8c9184b73661faffef19f5c";
            }
          else if prev.stdenv.isDarwin && prev.stdenv.isAarch64 then
            prev.fetchurl {
              url = "https://github.com/openai/codex/releases/download/rust-v${version}/codex-aarch64-apple-darwin.zst";
              sha256 = "50f3380d7f07bb1550e2bc9bd494ca8a350801f724da732076de0abd12e0736e";
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
