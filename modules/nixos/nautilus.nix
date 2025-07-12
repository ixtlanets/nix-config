{
  pkgs,
  ...
}:
{
  environment.systemPackages = with pkgs; [ nautilus ];
  services.gnome.sushi.enable = true;
  services.gvfs.enable = true;
}
