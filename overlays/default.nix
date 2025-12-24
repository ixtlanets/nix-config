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
      version = "0.77.0";
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
            sha256 = "sha256:95239c16fc26e7a5dae01828370e6cbc62feb991c4502a4c7f7226d721187556";
          }
        else if prev.stdenv.isLinux && prev.stdenv.isAarch64 then
          prev.fetchurl {
            url = "https://github.com/openai/codex/releases/download/rust-v${version}/codex-aarch64-unknown-linux-musl.zst";
            sha256 = "sha256:583565a88d3fbb288288662e35663d217285bcafbaf8149545348e7f0fecea31";
          }
        else if prev.stdenv.isDarwin && prev.stdenv.isx86_64 then
          prev.fetchurl {
            url = "https://github.com/openai/codex/releases/download/rust-v${version}/codex-x86_64-apple-darwin.zst";
            sha256 = "sha256:4dd08f45e1f980bd3ca57e6b6398eaaa66a16f05d5bbb9cadb8ea693b4c9d2f1";
          }
        else if prev.stdenv.isDarwin && prev.stdenv.isAarch64 then
          prev.fetchurl {
            url = "https://github.com/openai/codex/releases/download/rust-v${version}/codex-aarch64-apple-darwin.zst";
            sha256 = "sha256:020b5445eece807277dbe638669558fef4babfba009f82314e5fa575e8761143";
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
