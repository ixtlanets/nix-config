{
  lib,
  python3,
  fetchFromGitHub,
}:
let
  google-genai = import ./google-genai.nix { inherit lib python3 fetchFromGitHub; };
  pdftext = import ./pdftext.nix { inherit lib python3 fetchFromGitHub; };
  surya-ocr = import ./surya-ocr.nix { inherit lib python3 fetchFromGitHub; };
in
python3.pkgs.buildPythonApplication {
  pname = "marker-pdf";
  version = "unstable-2025-02-13";
  pyproject = true;

  src = fetchFromGitHub {
    owner = "VikParuchuri";
    repo = "marker";
    rev = "776b5183c6d3f75b9bd314349e78a452ffd84981";
    hash = "sha256-68anNvURs5jxNb6p405iHmEJc3UnZ5hUMwfyF3nLofo=";
  };

  build-system = [
    python3.pkgs.poetry-core
  ];

  dependencies = with python3.pkgs; [
    click
    filetype
    ftfy
    google-genai
    markdown2
    markdownify
    pdftext
    pillow
    pydantic
    pydantic-settings
    python-dotenv
    rapidfuzz
    regex
    scikit-learn
    surya-ocr
    torch
    tqdm
    transformers
  ];

  pythonImportsCheck = [
    "marker"
  ];

  meta = {
    description = "Convert PDF to markdown + JSON quickly with high accuracy";
    homepage = "https://github.com/VikParuchuri/marker";
    license = lib.licenses.gpl3Only;
    maintainers = with lib.maintainers; [ ];
    mainProgram = "marker-pdf";
  };
}
