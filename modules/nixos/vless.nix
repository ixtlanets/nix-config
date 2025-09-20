{
  lib,
  pkgs,
  config,
  ...
}:
let
  inherit (lib)
    mkEnableOption
    mkIf
    mkOption
    types
    ;
  cfg = config.services.vless;
  serviceName = cfg.serviceName;
  runtimeDir = "/run/${serviceName}";
  runtimeConfig = "${runtimeDir}/config.json";
  prepareConfigCommands =
    if cfg.configUser == null then
      [
        ''${pkgs.coreutils}/bin/install -Dm0400 ${lib.escapeShellArg cfg.configPath} ${lib.escapeShellArg runtimeConfig}''
      ]
    else
      let
        stageConfigScript = pkgs.writeShellScript "stage-${serviceName}-config" ''
          set -euo pipefail

          ${pkgs.coreutils}/bin/install -d -m 700 ${lib.escapeShellArg runtimeDir}
          umask 077
          ${pkgs.util-linux}/bin/runuser -u ${lib.escapeShellArg cfg.configUser} -- ${pkgs.coreutils}/bin/cat ${lib.escapeShellArg cfg.configPath} > ${lib.escapeShellArg runtimeConfig}
          ${pkgs.coreutils}/bin/chmod 0400 ${lib.escapeShellArg runtimeConfig}
        '';
      in
      [ stageConfigScript ];
in
{
  options.services.vless = {
    enable = mkEnableOption "VLESS tunnel managed by sing-box";

    configPath = mkOption {
      type = types.str;
      example = "/etc/nekoray/vless.json";
      description = ''Absolute path to the sing-box JSON configuration on disk. The file is exposed to the service under /run/${serviceName}/config.json.'';
    };

    package = mkOption {
      type = types.package;
      default = pkgs.sing-box;
      defaultText = "pkgs.sing-box";
      description = "Sing-box package to run the VLESS tunnel.";
    };

    configUser = mkOption {
      type = types.nullOr types.str;
      default = null;
      example = "nik";
      description = ''User that can read the sing-box configuration file when the service itself cannot (for example, if the file lives on a FUSE mount without allow_other). When set, the configuration is staged using this user before the service starts.'';
    };

    serviceName = mkOption {
      type = types.str;
      default = "vless-sing-box";
      description = "Systemd service name exposed by the CLI wrapper.";
    };

    autoStart = mkOption {
      type = types.bool;
      default = false;
      description = "Whether to start the VLESS tunnel automatically at boot.";
    };
  };

  config = mkIf cfg.enable {
    assertions = [
      {
        assertion = cfg.configPath != "";
        message = "services.vless.configPath must be set to the sing-box configuration file.";
      }
    ];

    environment.systemPackages = [
      (pkgs.writeShellScriptBin "vless" ''
        set -euo pipefail

        usage() {
          cat <<'HELP'
        Usage: vless [up|down|status]

        Without arguments an interactive selector is shown when gum is available.
        HELP
        }

        SERVICE=${lib.escapeShellArg serviceName}

        if [ "$#" -gt 1 ]; then
          usage >&2
          exit 1
        fi

        if [ "$#" -eq 1 ]; then
          choice=$1
        else
          if command -v gum >/dev/null 2>&1; then
            choice=$(gum choose --header="VLESS" up down status)
          else
            usage >&2
            exit 1
          fi
        fi

        case "$choice" in
          up)
            sudo systemctl start "$SERVICE"
            ;;
          down)
            sudo systemctl stop "$SERVICE"
            ;;
          status)
            systemctl status "$SERVICE"
            ;;
          *)
            usage >&2
            exit 1
            ;;
        esac
      '')
    ];

    systemd.services.${serviceName} = {
      description = "VLESS tunnel via sing-box";
      wants = [ "network-online.target" ];
      after = [ "network-online.target" ];
      wantedBy = lib.mkIf cfg.autoStart [ "multi-user.target" ];
      path = [
        pkgs.iproute2
        pkgs.coreutils
      ];
      serviceConfig = {
        Type = "simple";
        ExecStart = ''${cfg.package}/bin/sing-box run --disable-color -c ${lib.escapeShellArg runtimeConfig}'';
        ExecStartPre = prepareConfigCommands;
        Restart = "on-failure";
        RestartSec = 5;
        CapabilityBoundingSet = [
          "CAP_NET_ADMIN"
          "CAP_NET_BIND_SERVICE"
          "CAP_SETUID"
          "CAP_SETGID"
        ];
        AmbientCapabilities = [
          "CAP_NET_ADMIN"
          "CAP_NET_BIND_SERVICE"
        ];
        NoNewPrivileges = cfg.configUser == null;
        DeviceAllow = [
          "/dev/net/tun rw"
        ];
        RuntimeDirectory = serviceName;
        StateDirectory = serviceName;
        LimitNOFILE = 65535;
      };
      unitConfig = {
        StartLimitBurst = 5;
        StartLimitIntervalSec = 60;
      };
    };
  };
}
