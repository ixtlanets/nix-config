{
  lib,
  stdenv,
  fetchzip,
}:
stdenv.mkDerivation rec {
  pname = "opencode";
  version = "1.0.2";

  src =
    if stdenv.isLinux && stdenv.isx86_64 then
      fetchzip {
        url = "https://github.com/sst/opencode/releases/download/v${version}/opencode-linux-x64.zip";
        sha256 = "sha256-tbTkw/T6a2OSHr55Gg63if68YPJhxdmhh3/KY4/U5Fs=";
        stripRoot = false;
      }
    else if stdenv.isLinux && stdenv.isAarch64 then
      fetchzip {
        url = "https://github.com/sst/opencode/releases/download/v${version}/opencode-linux-arm64.zip";
        sha256 = "sha256-yeJCB6sIcfjyLbdHdpE6N+S2HZXfKI+nC99nXApXQvw=";
        stripRoot = false;
      }
    else if stdenv.isDarwin && stdenv.isx86_64 then
      fetchzip {
        url = "https://github.com/sst/opencode/releases/download/v${version}/opencode-darwin-x64.zip";
        sha256 = "sha256-dBlVCQWlungJ2aNXP8dKN3EDSjNIRp/yVTNiqgQFqxs=";
        stripRoot = false;
      }
    else if stdenv.isDarwin && stdenv.isAarch64 then
      fetchzip {
        url = "https://github.com/sst/opencode/releases/download/v${version}/opencode-darwin-arm64.zip";
        sha256 = "sha256-dBTAtQd5E3anPoaJa2eV6t9l5MrfgKst0Rtvgio83JU=";
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
