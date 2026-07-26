{
  lib,
  stdenv,
  fetchzip,
}:
stdenv.mkDerivation rec {
  pname = "opencode";
  version = "1.18.5";

  src =
    if stdenv.isLinux && stdenv.isx86_64 then
      fetchzip {
        url = "https://github.com/anomalyco/opencode/releases/download/v${version}/opencode-linux-x64.tar.gz";
        sha256 = "sha256-IMLUySwHkwkPrBeGQSz7fclP+3sZcKVEa5gh0fapcXE=";
        stripRoot = false;
      }
    else if stdenv.isLinux && stdenv.isAarch64 then
      fetchzip {
        url = "https://github.com/anomalyco/opencode/releases/download/v${version}/opencode-linux-arm64.tar.gz";
        sha256 = "sha256-ZUDgICfgXqHlO7LRkuV6fJ1lBF2tL/Rty5ZwuTLBBPk=";
        stripRoot = false;
      }
    else if stdenv.isDarwin && stdenv.isx86_64 then
      fetchzip {
        url = "https://github.com/anomalyco/opencode/releases/download/v${version}/opencode-darwin-x64.zip";
        sha256 = "sha256-aSj/laeiMB7bP7JZy75SeChDVSUi/F+knXfQbmRLZVw=";
        stripRoot = false;
      }
    else if stdenv.isDarwin && stdenv.isAarch64 then
      fetchzip {
        url = "https://github.com/anomalyco/opencode/releases/download/v${version}/opencode-darwin-arm64.zip";
        sha256 = "sha256-/Wq6q7S3sUmpAruSOJIM3pNRF+OvwHK6ikLEALT/lIc=";
        stripRoot = false;
      }
    else
      throw "Unsupported system for opencode";

  dontUnpack = false;

  # The binary bundles Bun with extra data; stripping it would drop the
  # embedded payload and leave only the Bun runtime in the output.
  dontStrip = true;

  installPhase = ''
    runHook preInstall
    mkdir -p $out/bin
    cp opencode $out/bin/
    chmod +x $out/bin/opencode
    runHook postInstall
  '';

  meta = {
    description = "The AI coding agent built for the terminal";
    homepage = "https://opencode.ai";
    license = lib.licenses.mit;
    maintainers = [ ];
    mainProgram = "opencode";
    platforms = [
      "x86_64-linux"
      "aarch64-linux"
      "x86_64-darwin"
      "aarch64-darwin"
    ];
  };
}
