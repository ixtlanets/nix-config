{ lib
, python3Packages
, fetchFromGitHub
}:

python3Packages.buildPythonApplication rec {
  pname = "specify-cli";
  version = "0.0.17";
  format = "pyproject";

  src = fetchFromGitHub {
    owner = "github";
    repo = "spec-kit";
    rev = "v${version}";
    hash = "sha256-1q23abg8xy1m0j6zqkhkfc0l16p5lvakjh3a9n16k28qr9qsc87h";
  };

  propagatedBuildInputs = with python3Packages; [
    typer
    rich
    httpx
    platformdirs
    readchar
    truststore
  ] ++ [
    httpx-socks
  ];

  meta = {
    description = "Specify CLI for Spec-Driven Development";
    homepage = "https://github.com/github/spec-kit";
    license = lib.licenses.mit;
    maintainers = [ ];
    mainProgram = "specify";
  };
}