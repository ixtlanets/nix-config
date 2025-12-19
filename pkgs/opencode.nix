{
  lib,
  stdenv,
  fetchzip,
}:
stdenv.mkDerivation rec {
  pname = "opencode";
  version = "1.0.168";

  src =
    if stdenv.isLinux && stdenv.isx86_64 then
      fetchzip {
        url = "https://github.com/sst/opencode/releases/download/v${version}/opencode-linux-x64.tar.gz";
        sha256 = "sha256:e752c6db2a048cd884d90b5aa25096389a56c21ca424f3ff809ef4c91ce10799";
        stripRoot = false;
      }
    else if stdenv.isLinux && stdenv.isAarch64 then
      fetchzip {
        url = "https://github.com/sst/opencode/releases/download/v${version}/opencode-linux-arm64.tar.gz";
        sha256 = "sha256:d645341fce8fe20cef27435e87d2a1803b033bc6354f2e48cf6349974f5e334f";
        stripRoot = false;
      }
    else if stdenv.isDarwin && stdenv.isx86_64 then
      fetchzip {
        url = "https://github.com/sst/opencode/releases/download/v${version}/opencode-darwin-x64.zip";
        sha256 = "sha256:49974f868740e35d33c87cb69f4457d15c49b7516a598ea857d2955666604f0b";
        stripRoot = false;
      }
    else if stdenv.isDarwin && stdenv.isAarch64 then
      fetchzip {
        url = "https://github.com/sst/opencode/releases/download/v${version}/opencode-darwin-arm64.zip";
        sha256 = "sha256-WCsbk9PxCdF9ID77Q+mwupumE2F/gE9HjQcZjgN0DzU=";
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
  };
}
