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
    hash = "sha256-8CCmccoYiWmCTWpAOdWm5ZpAAXMTTvyNBDX4jt5SQ+A=";
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