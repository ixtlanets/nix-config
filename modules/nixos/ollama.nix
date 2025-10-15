{ lib, config, ... }:
let
  defaultOriginAllowList = "chrome-extension://*";
in
{
  config = lib.mkIf config.services.ollama.enable {
    systemd.services.ollama.environment.OLLAMA_ORIGINS =
      lib.mkDefault defaultOriginAllowList;
  };
}
