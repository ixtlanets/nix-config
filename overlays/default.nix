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
    tawm = inputs.tawm.packages.${prev.stdenv.hostPlatform.system}.default;
    # nss_wrapper is Linux-only and its store path is referenced in mailutils' preCheck hook.
    # Nix tracks all store paths in derivation attrs, so even with doCheck=false it tries to build it.
    # Clear preCheck on Darwin to drop the reference entirely.
    mailutils = if prev.stdenv.isDarwin then
      prev.mailutils.overrideAttrs (_old: {
        preCheck = "";
      })
    else
      prev.mailutils;
    codex = prev.codex.overrideAttrs (old: rec {
      version = "0.125.0";
      buildType = "simple";
      patchPhase = ":";
      cargoSetupPostPatchHook = ":";
      nativeBuildInputs = [
        prev.zstd
        prev.makeWrapper
      ];
      src =
        if prev.stdenv.isLinux && prev.stdenv.isx86_64 then
          prev.fetchurl {
            url = "https://github.com/openai/codex/releases/download/rust-v${version}/codex-x86_64-unknown-linux-musl.zst";
            sha256 = "sha256:6b3a751d554197f163a57a440aba86aa4960a1457802a3efaa81e00dca9df6db";
          }
        else if prev.stdenv.isLinux && prev.stdenv.isAarch64 then
          prev.fetchurl {
            url = "https://github.com/openai/codex/releases/download/rust-v${version}/codex-aarch64-unknown-linux-musl.zst";
            sha256 = "sha256:30dd06c3d9b86785100ad78c9d468b60dee11968eee8c5dfdbf72a3c7d5457b5";
          }
        else if prev.stdenv.isDarwin && prev.stdenv.isx86_64 then
          prev.fetchurl {
            url = "https://github.com/openai/codex/releases/download/rust-v${version}/codex-x86_64-apple-darwin.zst";
            sha256 = "sha256:1e93c0cb1f07dcc08da8982bfc4393453a6327328f9ba8cbef52821c69bc1649";
          }
        else if prev.stdenv.isDarwin && prev.stdenv.isAarch64 then
          prev.fetchurl {
            url = "https://github.com/openai/codex/releases/download/rust-v${version}/codex-aarch64-apple-darwin.zst";
            sha256 = "sha256:41703b1ae133ddd15d9491b21a2cefdbb248b5fffd6322e835f0b846b6f577ba";
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
      system = final.stdenv.hostPlatform.system;
      config.allowUnfree = true;
    };
  };

  # Expose antigravity overlay from upstream input
  antigravity = inputs.antigravity-nix.overlays.default;

}
