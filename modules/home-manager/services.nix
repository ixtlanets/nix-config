{
  lib,
  config,
  pkgs,
  ...
}:
let
  mountPoint = "${config.home.homeDirectory}/goar-lbrand";
  rcloneConfig = "${config.xdg.configHome}/rclone/rclone.conf";
  rcloneConfigSecret = "${config.home.homeDirectory}/nix-config/secrets/rclone/rclone.conf";
in
{
  home.packages = lib.optionals pkgs.stdenv.isLinux [ pkgs.rclone ];

  xdg.configFile."rclone/rclone.conf" = lib.mkIf pkgs.stdenv.isLinux {
    source = config.lib.file.mkOutOfStoreSymlink rcloneConfigSecret;
    force = true;
  };

  services.syncthing.enable = true;
  # Nicely reload system units when changing configs
  systemd.user.startServices = "sd-switch";

  systemd.user.services.rclone-goar-lbrand = lib.mkIf pkgs.stdenv.isLinux {
    Unit = {
      Description = "Manually mount goar-lbrand Google Drive";
      ConditionPathExists = rcloneConfig;
    };

    Service = {
      Type = "simple";
      Environment = "PATH=/run/wrappers/bin:${pkgs.fuse3}/bin";
      ExecStartPre = "${pkgs.coreutils}/bin/mkdir -p ${mountPoint}";
      ExecStart = ''
        ${pkgs.rclone}/bin/rclone mount goar-lbrand: ${mountPoint} \
          --config ${rcloneConfig} \
          --vfs-cache-mode writes \
          --log-level INFO
      '';
      ExecStop = "/run/wrappers/bin/fusermount3 -u ${mountPoint}";
      Restart = "on-failure";
      RestartSec = "10s";
    };
  };

  systemd.user.services.voxtype = {
    Unit = {
      Description = "Voxtype voice typing daemon";
      After = [ "graphical-session.target" ];
      PartOf = [ "graphical-session.target" ];
    };

    Service = {
      ExecStart = "${pkgs.voxtype-onnx}/bin/voxtype";
      Environment = "PATH=${
        lib.makeBinPath [
          pkgs.voxtype-onnx
          pkgs.coreutils
          pkgs.wtype
          pkgs.which
          pkgs.dotool
          pkgs.wl-clipboard
          pkgs.xclip
          pkgs.xdotool
        ]
      }";
      Restart = "on-failure";
      RestartSec = 3;
    };

    Install.WantedBy = [ "graphical-session.target" ];
  };
}
