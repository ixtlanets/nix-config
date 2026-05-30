{ lib }:
let
  words = builtins.fromJSON (builtins.readFile ../../dotfiles/voice-typing/words.json);
  inherit (words) handyCustomWords voxtypeReplacements;

  replacementWords = lib.unique (builtins.attrValues voxtypeReplacements);
  missingHandyWords = builtins.filter (word: !(builtins.elem word handyCustomWords)) replacementWords;
in
assert lib.assertMsg (missingHandyWords == [ ])
  "dotfiles/voice-typing/words.json: handyCustomWords is missing values from voxtypeReplacements: ${builtins.concatStringsSep ", " missingHandyWords}";
{
  inherit handyCustomWords voxtypeReplacements;
}
