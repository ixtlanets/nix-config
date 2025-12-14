{ pkgs, ... }:
{
  home.sessionVariables = {
    OLLAMA_SERVICE_URL = "http://localhost:11434";
  };
}
