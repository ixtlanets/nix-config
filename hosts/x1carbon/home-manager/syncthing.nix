{ ... }:
let
  state = import ./syncthing-captured-state.nix;

  mobileShares = {
    "3y3qt-shfv6" = [
      "android-phone"
      "android-tablet"
    ];
    "lavhv-cjakz" = [ ];
    "wallpapers" = [ ];
    "разведмобиль" = [ ];
  };

  mkFolder = folder: {
    name = folder.id;
    value = {
      label = if folder ? label then folder.label else folder.id;
      path = folder.path;
      type = folder.type;
      devices = state.computerDevices ++ (mobileShares.${folder.id} or [ ]);
    };
  };
in
{
  services.syncthing = {
    enable = true;
    cert = "/home/nik/nix-config/secrets/syncthing/x1carbon/cert.pem";
    key = "/home/nik/nix-config/secrets/syncthing/x1carbon/key.pem";
    extraOptions = [ "--home=/home/nik/.local/state/syncthing" ];
    overrideDevices = true;
    overrideFolders = true;

    settings = {
      devices = builtins.mapAttrs (_name: id: { inherit id; }) state.devices;
      folders = builtins.listToAttrs (map mkFolder (builtins.attrValues state.folders));
    };
  };
}
