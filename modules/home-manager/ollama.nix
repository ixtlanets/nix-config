{ pkgs, ... }:
{
  nixpkgs = {
    # You can add overlays here
    overlays = [
      (final: prev: {
        ollamagpu = pkgs.unstable.ollama.override { llama-cpp = (pkgs.unstable.llama-cpp.override { cudaSupport = true; }); };
      })

    ];
  };

  home.packages = with pkgs; [
    ollamagpu
  ];
}

