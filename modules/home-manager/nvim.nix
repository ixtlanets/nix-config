
{ inputs, outputs, lib, config, pkgs, ... }:
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
      prisma-engines # ditto for schema.prisma files
      nixpkgs-fmt
      lua-language-server
      gnumake
      luajitPackages.jsregexp
      nodePackages.eslint_d # js/ts code formatter and linter
      nodePackages.prettier # ditto
      nodePackages.vscode-langservers-extracted # lsp servers for json, html, css
      nodePackages.svelte-language-server
      nodePackages.diagnostic-languageserver
      nodePackages.typescript-language-server
      nodePackages.bash-language-server
      nodePackages."@tailwindcss/language-server"
  ];
  programs = {
    neovim = {
      enable = true;
      viAlias = true;
      vimAlias = true;
      withNodeJs = true;
      withRuby = true;
      withPython3 = true;
      plugins = with pkgs.vimPlugins; [
        LazyVim
      ];
    };
  };
}
