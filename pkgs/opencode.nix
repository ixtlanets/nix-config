{
  lib,
  stdenv,
  fetchzip,
}:
stdenv.mkDerivation rec {
  pname = "opencode";
  version = "0.10.3";

  src =
    if stdenv.isLinux && stdenv.isx86_64 then
      fetchzip {
        url = "https://github.com/sst/opencode/releases/download/v${version}/opencode-linux-x64.zip";
        sha256 = "sha256-zAcz/jJ07Hgi209EnTSABvY8A2j3NrkPIGrTdeHcGhk=";
        stripRoot = false;
      }
    else if stdenv.isLinux && stdenv.isAarch64 then
      fetchzip {
        url = "https://github.com/sst/opencode/releases/download/v${version}/opencode-linux-arm64.zip";
        sha256 = "sha256-lkuSlPPl0ha7PKB/4NalzplX0edzoTYSiFv+Fv4dXjc=";
        stripRoot = false;
      }
    else if stdenv.isDarwin && stdenv.isx86_64 then
      fetchzip {
        url = "https://github.com/sst/opencode/releases/download/v${version}/opencode-darwin-x64.zip";
        sha256 = "sha256-ytiseQu4dO/Y1s2v4In5D4nn95DzAf892pxhQocpjaw=";
        stripRoot = false;
      }
    else if stdenv.isDarwin && stdenv.isAarch64 then
      fetchzip {
        url = "https://github.com/sst/opencode/releases/download/v${version}/opencode-darwin-arm64.zip";
        sha256 = "sha256-xXRyht6XxhiNTUbHiVbUYV0Ab0DZnPJ7I+vyiHkQaeU=";
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
