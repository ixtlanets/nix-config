{
  lib,
  stdenv,
  fetchzip,
}:
stdenv.mkDerivation rec {
  pname = "opencode";
  version = "0.9.11";

  src =
    if stdenv.isLinux && stdenv.isx86_64 then
      fetchzip {
        url = "https://github.com/sst/opencode/releases/download/v${version}/opencode-linux-x64.zip";
        sha256 = "b43ff31dcb80964640d6f335312a8a361135c2063775062f9bca7f28096f40cd";
        stripRoot = false;
      }
    else if stdenv.isLinux && stdenv.isAarch64 then
      fetchzip {
        url = "https://github.com/sst/opencode/releases/download/v${version}/opencode-linux-arm64.zip";
        sha256 = "fc231d3b233821bfba2c60fc4322fbab8bde5ab138752f11e0694ca73e02a36b";
        stripRoot = false;
      }
    else if stdenv.isDarwin && stdenv.isx86_64 then
      fetchzip {
        url = "https://github.com/sst/opencode/releases/download/v${version}/opencode-darwin-x64.zip";
        sha256 = "26353cee1af08715ca77dab2c66771d66b5b479148c9912e10c0352035a030af";
        stripRoot = false;
      }
    else if stdenv.isDarwin && stdenv.isAarch64 then
      fetchzip {
        url = "https://github.com/sst/opencode/releases/download/v${version}/opencode-darwin-arm64.zip";
        sha256 = "86f1597380e2fa7ce6f9afb170b4de099674a567d33a3d3fcd648de2de93b93a";
        stripRoot = false;
      }
    else throw "Unsupported system for opencode";

  dontUnpack = false;

  installPhase = ''
    mkdir -p $out/bin
    cp opencode $out/bin/
    chmod +x $out/bin/opencode
  '';

  meta = {
    description = "The AI coding agent built for the terminal";
    homepage = "https://opencode.ai";
    license = lib.licenses.unfree; # Assuming, as it's a commercial tool
    maintainers = [ ];
    mainProgram = "opencode";
  };
}
