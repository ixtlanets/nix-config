{
  lib,
  stdenv,
  fetchurl,
  nodejs,
}:

stdenv.mkDerivation rec {
  pname = "codebuddy-code";
  version = "1.0.14";

  src = fetchurl {
    url = "https://registry.npmjs.org/@tencent-ai/codebuddy-code/-/codebuddy-code-${version}.tgz";
    hash = "sha256-qdg5B/lN29SC5jGyZE7DxgiOz9fcU+pV1HN4r7YfFWo=";
  };

  buildInputs = [ nodejs ];

  installPhase = ''
    mkdir -p $out/bin
    cp -r . $out/libexec
    ln -s $out/libexec/bin/codebuddy $out/bin/codebuddy
  '';

  meta = {
    description = "CodeBuddy Code is Tencent Cloud's official intelligent coding tool, supporting efficient collaboration and development through natural language in terminals, IDEs, and GitHub.";
    homepage = "https://cnb.cool/codebuddy/codebuddy-code";
    license = lib.licenses.unfree; # SEE LICENSE IN README.md
    maintainers = [ ];
    mainProgram = "codebuddy";
  };
}