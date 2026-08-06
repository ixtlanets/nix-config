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
    opencode-desktop = final.callPackage ../pkgs/opencode-desktop.nix { };
    voxtype = final.callPackage ../pkgs/voxtype.nix { voxtype = prev.voxtype; };
    voxtype-onnx = final.callPackage ../pkgs/voxtype.nix { voxtype = prev.voxtype-onnx; };
    voxtype-vulkan = final.callPackage ../pkgs/voxtype.nix { voxtype = prev.voxtype-vulkan; };
  };

  # Included upstream after the locked nixpkgs revision (NixOS/nixpkgs#549253).
  hyprland-fix = _final: prev: {
    hyprland = prev.hyprland.overrideAttrs (old: {
      postPatch = ''
        substituteInPlace CMakeLists.txt start/CMakeLists.txt hyprpm/CMakeLists.txt \
          --replace-fail "glaze 7...<8" "glaze"
      '' + old.postPatch;
    });
  };

  # This one contains whatever you want to overlay
  # You can change versions, add patches, set compilation flags, anything really.
  # https://nixos.wiki/wiki/Overlays
  modifications = final: prev: {
    tawm = inputs.tawm.packages.${prev.stdenv.hostPlatform.system}.default;
    gam = prev.gam.overridePythonAttrs (_: {
      pythonRelaxDeps = [ "chardet" ];
    });
    imgp = prev.imgp.overridePythonAttrs (old: {
      build-system = old.build-system ++ [
        (final.python3Packages.standard-pkg-resources.overridePythonAttrs (_: {
          doCheck = !prev.stdenv.isDarwin;
        }))
      ];
    });
    python3 =
      if prev.stdenv.isDarwin then
        prev.python3.override {
          packageOverrides = _pythonFinal: pythonPrev: {
            jupyter-server = pythonPrev.jupyter-server.overridePythonAttrs (old: {
              disabledTests = (old.disabledTests or [ ]) ++ [
                "test_disconnect_resolves_orphaned_kernel_info_future"
              ];
            });
          };
        }
      else
        prev.python3;
    # nss_wrapper is Linux-only and its store path is referenced in mailutils' preCheck hook.
    # Nix tracks all store paths in derivation attrs, so even with doCheck=false it tries to build it.
    # Clear preCheck on Darwin to drop the reference entirely.
    mailutils =
      if prev.stdenv.isDarwin then
        prev.mailutils.overrideAttrs
          (_old: {
            preCheck = "";
          })
      else
        prev.mailutils;
    codex = prev.stdenvNoCC.mkDerivation rec {
      pname = "codex";
      version = "0.146.1";
      nativeBuildInputs = [
        prev.zstd
        prev.makeWrapper
      ];
      src =
        if prev.stdenv.isLinux && prev.stdenv.isx86_64 then
          prev.fetchurl
            {
              url = "https://github.com/openai/codex/releases/download/rust-v${version}/codex-x86_64-unknown-linux-musl.zst";
              sha256 = "sha256-yWnPnRPBN8xAGL9mtoMmq04iBFLopqjdZzkltAgX/ec=";
            }
        else if prev.stdenv.isLinux && prev.stdenv.isAarch64 then
          prev.fetchurl
            {
              url = "https://github.com/openai/codex/releases/download/rust-v${version}/codex-aarch64-unknown-linux-musl.zst";
              sha256 = "sha256-F6u73GiG9gp6vpVT2lE+K62HR3+AgQnJdrEf3KM+C5I=";
            }
        else if prev.stdenv.isDarwin && prev.stdenv.isx86_64 then
          prev.fetchurl
            {
              url = "https://github.com/openai/codex/releases/download/rust-v${version}/codex-x86_64-apple-darwin.zst";
              sha256 = "sha256-H8Fw5XjRRSfJSJeSjQVzY7BzBEXrN5iHU4tpwx0v1RA=";
            }
        else if prev.stdenv.isDarwin && prev.stdenv.isAarch64 then
          prev.fetchurl
            {
              url = "https://github.com/openai/codex/releases/download/rust-v${version}/codex-aarch64-apple-darwin.zst";
              sha256 = "sha256-tTfAOpgopISWytXg03Y8QhVF3jNfjLAxIBO4IyOURBk=";
            }
        else
          throw "Unsupported system for codex";
      dontUnpack = true;
      installPhase = ''
        runHook preInstall

        mkdir -p $out/bin
        zstd -d --stdout $src > $out/bin/codex
        chmod +x $out/bin/codex

        runHook postInstall
      '';
      meta = prev.codex.meta;
    };
    # direnv 2.37.1 checkPhase hangs on Darwin while running shell export tests.
    direnv =
      if prev.stdenv.isDarwin then
        prev.direnv.overrideAttrs
          (_old: {
            doCheck = false;
          })
      else
        prev.direnv;
    # Ensure the client understands GSSAPI directives in system ssh_config (e.g., WSL).
    openssh =
      if prev.stdenv.isLinux then
        prev.openssh.override
          {
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
