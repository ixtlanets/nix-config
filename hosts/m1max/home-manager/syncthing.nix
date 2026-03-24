import ../../../modules/home-manager/syncthing-topology.nix {
  cert = "/Users/nik/Library/Application Support/Syncthing/cert.pem";
  key = "/Users/nik/Library/Application Support/Syncthing/key.pem";
  syncthingHome = "/Users/nik/Library/Application Support/Syncthing";
  folderPaths = {
    "3y3qt-shfv6" = "/Users/nik/obsidian-vault";
    "lavhv-cjakz" = "/Users/nik/Documents/Проекты";
    wallpapers = "/Users/nik/wallpapers";
    "разведмобиль" = "/Users/nik/Documents/разведмобиль";
  };
}
