{
  lib,
  stdenvNoCC,
  fetchurl,
}:
let
  version = "2026.9.5";
  sources = {
    aarch64-darwin = fetchurl {
      url = "https://github.com/jdx/mise/releases/download/v${version}/mise-v${version}-macos-arm64";
      hash = "sha256-YnS2gSKoN8UUN06W2rsYqeNWK90oUotLP+6p2OthXZg=";
    };
    x86_64-darwin = fetchurl {
      url = "https://github.com/jdx/mise/releases/download/v${version}/mise-v${version}-macos-x64";
      hash = "sha256-1g5QM0YYim48vrnGo91VwTdoacjxlmdgT3l44ZpW93w=";
    };
    aarch64-linux = fetchurl {
      url = "https://github.com/jdx/mise/releases/download/v${version}/mise-v${version}-linux-arm64";
      hash = "sha256-NyHUQlPQoBRUXrH+EyWDM9onC5jYx1I+B+dhnnTi938=";
    };
    x86_64-linux = fetchurl {
      url = "https://github.com/jdx/mise/releases/download/v${version}/mise-v${version}-linux-x64";
      hash = "sha256-MvZE2MKRuxgvcCxtKw3an4sBRB6UDXTTKKrV8IRGsv0=";
    };
  };
in
stdenvNoCC.mkDerivation {
  pname = "mise";
  inherit version;

  src = sources.${stdenvNoCC.hostPlatform.system} or (throw "Unsupported system for mise");

  dontUnpack = true;
  dontBuild = true;
  dontStrip = true;

  installPhase = ''
    runHook preInstall
    install -Dm755 "$src" "$out/bin/mise"
    runHook postInstall
  '';

  meta = {
    description = "Front-end to your dev env";
    homepage = "https://mise.jdx.dev";
    license = lib.licenses.mit;
    maintainers = [ ];
    mainProgram = "mise";
    platforms = builtins.attrNames sources;
    sourceProvenance = [ lib.sourceTypes.binaryNativeCode ];
  };
}
