{
  config,
  lib,
  pkgs,
  ...
}:
let
  cfg = config.services.vaultwardenBackupPull;
in
{
  options.services.vaultwardenBackupPull = {
    enable = lib.mkEnableOption "pull encrypted Vaultwarden backups from london";

    calendar = lib.mkOption {
      type = lib.types.str;
      default = "*-*-* 04:00:00";
      description = "systemd OnCalendar value for pulling backups.";
    };

    destination = lib.mkOption {
      type = lib.types.str;
      default = "${config.home.homeDirectory}/backups/vaultwarden/london";
      description = "Local directory for encrypted Vaultwarden backup artifacts.";
    };

    host = lib.mkOption {
      type = lib.types.str;
      default = "ubuntu@london";
      description = "SSH host used to pull encrypted backups.";
    };

    randomizedDelaySec = lib.mkOption {
      type = lib.types.str;
      default = "2h";
      description = "Randomized delay for the pull timer.";
    };

    remotePath = lib.mkOption {
      type = lib.types.str;
      default = "/var/backups/vaultwarden";
      description = "Remote directory containing encrypted Vaultwarden backup artifacts.";
    };

    retentionDays = lib.mkOption {
      type = lib.types.ints.positive;
      default = 180;
      description = "Number of days to retain local encrypted backup artifacts.";
    };
  };

  config = lib.mkIf cfg.enable {
    home.packages = with pkgs; [
      openssh
      rsync
    ];

    systemd.user.services.vaultwarden-backup-pull = {
      Unit = {
        Description = "Pull encrypted Vaultwarden backups from london";
        Wants = [ "network-online.target" ];
        After = [ "network-online.target" ];
      };

      Service = {
        Type = "oneshot";
        ExecStart = lib.getExe (
          pkgs.writeShellApplication {
            name = "vaultwarden-backup-pull";
            runtimeInputs = with pkgs; [
              coreutils
              findutils
              openssh
              rsync
            ];
            text = ''
              set -euo pipefail

              dest=${lib.escapeShellArg cfg.destination}
              remote=${lib.escapeShellArg "${cfg.host}:${cfg.remotePath}/"}

              mkdir -p "$dest"
              rsync -av \
                --ignore-existing \
                --include='*.age' \
                --exclude='*' \
                "$remote" "$dest"/

              find "$dest" -type f -name '*.age' -mtime +${toString cfg.retentionDays} -delete
            '';
          }
        );
      };
    };

    systemd.user.timers.vaultwarden-backup-pull = {
      Unit.Description = "Pull encrypted Vaultwarden backups from london";

      Timer = {
        OnCalendar = cfg.calendar;
        Persistent = true;
        RandomizedDelaySec = cfg.randomizedDelaySec;
        Unit = "vaultwarden-backup-pull.service";
      };

      Install.WantedBy = [ "timers.target" ];
    };
  };
}
