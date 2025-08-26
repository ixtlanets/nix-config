# Shell for bootstrapping flake-enabled nix and home-manager
# You can enter it through 'nix develop' or (legacy) 'nix-shell'

{
  pkgs ? (import ./nixpkgs.nix) { },
}:
{
  default = pkgs.mkShell {
    # Enable experimental features without having to specify the argument
    NIX_CONFIG = "experimental-features = nix-command flakes";
    nativeBuildInputs = with pkgs; [
      nix
      home-manager
      git
    ];
  };
  jupyter = pkgs.mkShell {
    # Enable experimental features without having to specify the argument
    NIX_CONFIG = "experimental-features = nix-command flakes";
    packages = with pkgs; [
      jupyter
      python311Packages.pandas
      python311Packages.pandas-datareader
      python311Packages.yfinance
      python311Packages.matplotlib
      python311Packages.numpy
      python311Packages.tabulate
    ];
  };
}
