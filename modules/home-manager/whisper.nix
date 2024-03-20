{ pkgs, ... }:
{

  home.packages = with pkgs; [
    openai-whisper-cpp
    whisper-ctranslate2
  ];
}
