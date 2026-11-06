import ../../../modules/home-manager/syncthing-topology.nix {
  cert = "/Users/nik/nix-config/secrets/syncthing/m3max/cert.pem";
  key = "/Users/nik/nix-config/secrets/syncthing/m3max/key.pem";
  syncthingHome = "/Users/nik/Library/Application Support/Syncthing";
  folderPaths = {
    "lavhv-cjakz" = "/Users/nik/Documents/Проекты";
    wallpapers = "/Users/nik/wallpapers";
    "разведмобиль" = "/Users/nik/Documents/разведмобиль";
  };
}
