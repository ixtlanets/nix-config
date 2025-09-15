# Custom packages, that can be defined similarly to ones from nixpkgs
# You can build them using 'nix build .#example' or (legacy) 'nix-build -A example'

{
  pkgs ? (import ../nixpkgs.nix) { },
}:
{
  # example = pkgs.callPackage ./example { };
  marker-pdf = pkgs.callPackage ./marker-pdf.nix { };
  google-genai = pkgs.callPackage ./google-genai.nix { };
  pdftext = pkgs.callPackage ./pdftext.nix { };
  surya-ocr = pkgs.callPackage ./surya-ocr.nix { };
  codebuddy-code = pkgs.callPackage ./codebuddy-code.nix { };
}
