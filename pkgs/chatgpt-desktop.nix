{
  buildFHSEnv,
  dpkg,
  fetchurl,
  lib,
  stdenvNoCC,
  writeShellScript,
}:

let
  pname = "chatgpt";
  version = "26.803.81509";

  src = fetchurl {
    url = "https://persistent.oaistatic.com/codex-app-prod/linux/deb/latest/chatgpt_amd64.deb";
    hash = "sha256-qb+Ro2j598Tuo4CCqfuPtGuNAFtxmm13FdLloZgsOOs=";
  };

  chatgpt-unwrapped = stdenvNoCC.mkDerivation {
    pname = "${pname}-unwrapped";
    inherit version src;

    nativeBuildInputs = [ dpkg ];

    unpackPhase = ''
      runHook preUnpack
      dpkg-deb --extract $src .
      runHook postUnpack
    '';

    installPhase = ''
      runHook preInstall

      mkdir -p $out
      cp -r usr/lib usr/share $out/
      chmod -R a+rX $out

      runHook postInstall
    '';

    dontFixup = true;
  };

  chatgpt-launcher = writeShellScript "chatgpt-launcher" ''
    if [[ ''${XDG_SESSION_TYPE:-} == "wayland" ]]; then
      set -- --ozone-platform=wayland "$@"
    fi

    exec ${chatgpt-unwrapped}/lib/chatgpt/codex-launcher "$@"
  '';
in
buildFHSEnv {
  inherit pname version;

  runScript = chatgpt-launcher;

  targetPkgs =
    pkgs:
    with pkgs;
    [
      git
      glib
      libsecret
      xdg-utils
    ]
    ++ map lib.getLib [
      alsa-lib
      at-spi2-core
      atk
      cairo
      cups
      dbus
      expat
      gdk-pixbuf
      graphite2
      gtk3
      libdrm
      libgbm
      libglvnd
      libnotify
      libusb1
      libx11
      libxcb
      libxcomposite
      libxdamage
      libxext
      libxfixes
      libxkbcommon
      libxrandr
      nspr
      nss
      openssl
      pango
      stdenv.cc.cc
      udev
      vulkan-loader
      wayland
    ];

  extraInstallCommands = ''
    install -Dm444 \
      ${chatgpt-unwrapped}/share/applications/chatgpt.desktop \
      $out/share/applications/chatgpt.desktop
    install -Dm444 \
      ${chatgpt-unwrapped}/share/pixmaps/chatgpt.png \
      $out/share/pixmaps/chatgpt.png
  '';

  meta = {
    description = "ChatGPT desktop app with ChatGPT Work and Codex";
    homepage = "https://openai.com/codex/";
    license = lib.licenses.unfree;
    mainProgram = pname;
    platforms = [ "x86_64-linux" ];
    sourceProvenance = [ lib.sourceTypes.binaryNativeCode ];
  };
}
