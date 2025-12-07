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
    specify-cli = final.callPackage ../pkgs/specify-cli.nix { };
  };

  # This one contains whatever you want to overlay
  # You can change versions, add patches, set compilation flags, anything really.
  # https://nixos.wiki/wiki/Overlays
  modifications = final: prev: {
    tawm = inputs.tawm.packages.${prev.system}.default;
    codex = prev.codex.overrideAttrs (old: rec {
      version = "0.65.0";
      buildType = "simple";
      cargoSetupPostPatchHook = ":";
      nativeBuildInputs = [
        prev.zstd
        prev.makeWrapper
      ];
      src =
        if prev.stdenv.isLinux && prev.stdenv.isx86_64 then
          prev.fetchurl {
            url = "https://github.com/openai/codex/releases/download/rust-v${version}/codex-x86_64-unknown-linux-musl.zst";
            sha256 = "sha256:4b705f91d26e9c9726f861f5f76fc674fe4a8846dab25b75b1586cf263613a8b";
          }
        else if prev.stdenv.isLinux && prev.stdenv.isAarch64 then
          prev.fetchurl {
            url = "https://github.com/openai/codex/releases/download/rust-v${version}/codex-aarch64-unknown-linux-musl.zst";
            sha256 = "1a5fe2b500afe158afc297a905df46d518b7771660fc955b661c15ca2b5b50d6";
          }
        else if prev.stdenv.isDarwin && prev.stdenv.isx86_64 then
          prev.fetchurl {
            url = "https://github.com/openai/codex/releases/download/rust-v${version}/codex-x86_64-apple-darwin.zst";
            sha256 = "sha256-WZQUmEKDPhp6ZXOOyz+5zSFWxdNuCr99BzD1I4TYdp0=";
          }
        else if prev.stdenv.isDarwin && prev.stdenv.isAarch64 then
          prev.fetchurl {
            url = "https://github.com/openai/codex/releases/download/rust-v${version}/codex-aarch64-apple-darwin.zst";
            sha256 = "sha256:b1e3110ae44fb97d8ace4a632f1b2a13e835351c6636fbe72e2300ca5febe6b0";
          }
        else
          throw "Unsupported system for codex";
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

  # Expose antigravity overlay from upstream input
  antigravity = inputs.antigravity-nix.overlays.default;

}
