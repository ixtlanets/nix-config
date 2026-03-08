{ lib, config, ... }:
let
  defaultOriginAllowList = "chrome-extension://*";
  defaultContextLength = "65536";
in
{
  config = lib.mkIf config.services.ollama.enable {
    systemd.services.ollama.environment = {
      OLLAMA_CONTEXT_LENGTH = lib.mkDefault defaultContextLength;
      OLLAMA_ORIGINS = lib.mkDefault defaultOriginAllowList;
    };
  };
}
