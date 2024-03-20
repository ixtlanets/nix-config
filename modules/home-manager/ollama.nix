{ pkgs, ... }:
{
  nixpkgs = {
    # You can add overlays here
    overlays = [
      (final: prev: {
        ollamagpu = pkgs.unstable.ollama.override { acceleration = "cuda"; };
      })

    ];
  };

  home.packages = with pkgs; [
    ollamagpu
  ];
}
