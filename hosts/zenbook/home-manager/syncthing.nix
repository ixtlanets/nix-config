{ ... }:
{
  services.syncthing = {
    cert = "/home/nik/nix-config/secrets/syncthing/zenbook/cert.pem";
    key = "/home/nik/nix-config/secrets/syncthing/zenbook/key.pem";
    extraOptions = [ "--home=/home/nik/.local/state/syncthing" ];
  };
}
