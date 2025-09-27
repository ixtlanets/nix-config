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
        version = "0.41.0";
        buildType = "simple";
        cargoSetupPostPatchHook = ":";
        nativeBuildInputs = [ prev.zstd ];
        src =
          if prev.stdenv.isLinux && prev.stdenv.isx86_64 then
            prev.fetchurl {
              url = "https://github.com/openai/codex/releases/download/rust-v${version}/codex-x86_64-unknown-linux-musl.zst";
              sha256 = "4146cafd0f7a9eaf890ec68f1126a9a5a24a67b3524f73c3f7e5d06f858d2224";
            }
          else if prev.stdenv.isLinux && prev.stdenv.isAarch64 then
            prev.fetchurl {
              url = "https://github.com/openai/codex/releases/download/rust-v${version}/codex-aarch64-unknown-linux-musl.zst";
              sha256 = "a5be3aa61927e334cc0005cdc11c56f4f68a9c0631e70c6ca0f76a6f8c833466";
            }
          else if prev.stdenv.isDarwin && prev.stdenv.isAarch64 then
            prev.fetchurl {
              url = "https://github.com/openai/codex/releases/download/rust-v${version}/codex-aarch64-apple-darwin.zst";
              sha256 = "d3bcac43ea59d6bf75be199f8e31a4f512a292832d806aadc8fef971f9bb1c07";
            }
          else throw "Unsupported system for codex";
        dontUnpack = true;
        installPhase = "mkdir -p $out/bin && zstd -d $src -o $out/bin/codex && chmod +x $out/bin/codex";
      });
      # Ensure the client understands GSSAPI directives in system ssh_config (e.g., WSL).
      openssh =
        if prev.stdenv.isLinux then
          prev.openssh.override {
            withKerberos = true;
          }
        else
          prev.openssh;
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
