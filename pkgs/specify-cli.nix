{ lib
, python3Packages
, fetchFromGitHub
}:

python3Packages.buildPythonApplication rec {
  pname = "specify-cli";
  version = "0.0.54";
  format = "pyproject";

  src = fetchFromGitHub {
    owner = "github";
    repo = "spec-kit";
    rev = "v${version}";
    hash = "sha256-JanzqqcCVGRHtXXoc+hT7Xc4O7jg/gKuFISXr9N1L+A=";
  };

  nativeBuildInputs = with python3Packages; [
    hatchling
  ];

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