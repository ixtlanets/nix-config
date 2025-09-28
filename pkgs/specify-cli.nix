{ lib
, python3Packages
, fetchFromGitHub
}:

let
  truststore_0_10_4 = python3Packages.truststore.overridePythonAttrs (_: rec {
    version = "0.10.4";
    src = python3Packages.fetchPypi {
      pname = "truststore";
      inherit version;
      sha256 = "sha256-nZG9Q2RjrV5O5KunZmKN1s1wEM8+JGF1azMDcQ7rwwE=";
    };
  });
in

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

  propagatedBuildInputs =
    (with python3Packages; [
      typer
      rich
      httpx
      platformdirs
      readchar
      httpx-socks
    ]) ++ [
      truststore_0_10_4
    ];

  meta = {
    description = "Specify CLI for Spec-Driven Development";
    homepage = "https://github.com/github/spec-kit";
    license = lib.licenses.mit;
    maintainers = [ ];
    mainProgram = "specify";
  };
}
