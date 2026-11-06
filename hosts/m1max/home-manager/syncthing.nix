import ../../../modules/home-manager/syncthing-topology.nix {
  cert = "/Users/nik/nix-config/secrets/syncthing/m1max/cert.pem";
  key = "/Users/nik/nix-config/secrets/syncthing/m1max/key.pem";
  syncthingHome = "/Users/nik/Library/Application Support/Syncthing";
  folderPaths = {
    "lavhv-cjakz" = "/Users/nik/Documents/Проекты";
    wallpapers = "/Users/nik/wallpapers";
    "разведмобиль" = "/Users/nik/Documents/разведмобиль";
  };
}
