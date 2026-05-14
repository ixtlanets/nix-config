{
  appimageTools,
  fetchurl,
  lib,
  stdenv,
}:

let
  pname = "opencode-desktop";
  version = "1.14.50";

  src =
    if stdenv.isLinux && stdenv.isx86_64 then
      fetchurl {
        url = "https://github.com/anomalyco/opencode/releases/download/v${version}/opencode-desktop-linux-x86_64.AppImage";
        hash = "sha256-0awz3nZ2ZjfAcxHDmAAgeCXIfaaXAWi2sIiywN53wbI=";
      }
    else if stdenv.isLinux && stdenv.isAarch64 then
      fetchurl {
        url = "https://github.com/anomalyco/opencode/releases/download/v${version}/opencode-desktop-linux-arm64.AppImage";
        hash = "sha256-ZgIvGrZvYyKOpjxRn8u6v1TggHwr9/ffoNbEpOEJi6Y=";
      }
    else
      throw "Unsupported system for opencode-desktop";

  appimageContents = appimageTools.extractType2 { inherit pname version src; };
in
appimageTools.wrapType2 {
  inherit pname version src;

  extraInstallCommands = ''
    install -m 444 -D ${appimageContents}/@opencode-aidesktop.desktop \
      $out/share/applications/opencode.desktop
    substituteInPlace $out/share/applications/opencode.desktop \
      --replace-fail 'Exec=AppRun' 'Exec=${pname}'

    install -m 444 -D ${appimageContents}/@opencode-aidesktop.png \
      $out/share/pixmaps/@opencode-aidesktop.png

    if [ -d ${appimageContents}/usr/share/icons ]; then
      cp -r ${appimageContents}/usr/share/icons $out/share/
    fi
  '';

  meta = {
    description = "OpenCode desktop app";
    homepage = "https://opencode.ai/download";
    license = lib.licenses.mit;
    maintainers = [ ];
    mainProgram = pname;
    platforms = [
      "x86_64-linux"
      "aarch64-linux"
    ];
  };
}
