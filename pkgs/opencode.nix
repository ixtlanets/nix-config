{
  lib,
  stdenv,
  fetchzip,
}:
stdenv.mkDerivation rec {
  pname = "opencode";
  version = "1.0.204";

  src =
    if stdenv.isLinux && stdenv.isx86_64 then
      fetchzip {
        url = "https://github.com/sst/opencode/releases/download/v${version}/opencode-linux-x64.tar.gz";
        sha256 = "sha256:f845137f6ace485db45b22d18af8c77ec59bdf75ca22c5b36153747fafba4557";
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
        sha256 = "sha256-FZngPOIfx7wR4Kx/J1cI9F7+48duiDda+ynS2ETqbTw=";
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
