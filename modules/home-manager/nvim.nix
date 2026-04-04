{
  inputs,
  outputs,
  lib,
  config,
  pkgs,
  ...
}:
{
  home.packages = with pkgs; [
    fd
    ripgrep
    fzy
    cargo
    gcc
    go
    git
    lazygit
    curl # needed to fetch titles from urls
    vale # linter for prose
    proselint # ditto
    luaformatter # ditto for lua
    nixpkgs-fmt
    lua-language-server
    gnumake
    luajitPackages.jsregexp
    eslint_d
    prettier
    vscode-langservers-extracted
    svelte-language-server
    diagnostic-languageserver
    typescript-language-server
    bash-language-server
    tailwindcss-language-server
    lua
    luajitPackages.luarocks
    nixd
    nixfmt
    statix
  ];
  programs = {
    neovim = {
      defaultEditor = true;
      enable = true;
      viAlias = true;
      vimAlias = true;
      withNodeJs = true;
      withRuby = true;
      withPython3 = true;
    };
  };
}
