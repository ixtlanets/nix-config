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
  toggleScript = pkgs.writeShellScriptBin "vless-toggle" ''
    set -euo pipefail

    SERVICE=${lib.escapeShellArg serviceName}

    if [ "$#" -ne 1 ]; then
      printf 'Usage: vless-toggle [up|down]\n' >&2
      exit 1
    fi

    case "$1" in
      up)
        exec ${pkgs.systemd}/bin/systemctl start "$SERVICE"
        ;;
      down)
        exec ${pkgs.systemd}/bin/systemctl stop "$SERVICE"
        ;;
      *)
        printf 'Usage: vless-toggle [up|down]\n' >&2
        exit 1
        ;;
    esac
  '';
  waybarScript = pkgs.writeShellScriptBin "vless-waybar" ''
        set -euo pipefail

        SERVICE=${lib.escapeShellArg serviceName}
        CACHE_DIR="''${XDG_RUNTIME_DIR:-/run/user/$(${pkgs.coreutils}/bin/id -u)}/vless-waybar"
        IP_FILE="$CACHE_DIR/ip"
        TS_FILE="$CACHE_DIR/ip.ts"
        REFRESH_SECS=60

        escape_json() {
          local value=$1
          value=''${value//\\/\\\\}
          value=''${value//\"/\\\"}
          value=''${value//$'\n'/\\n}
          printf '%s' "$value"
        }

        print_json() {
          local text=$1
          local class=$2
          local tooltip=$3
          printf '{"text":"%s","class":"%s","tooltip":"%s"}\n' \
            "$(escape_json "$text")" \
            "$(escape_json "$class")" \
            "$(escape_json "$tooltip")"
        }

        service_exists() {
          ${pkgs.systemd}/bin/systemctl show "$SERVICE" >/dev/null 2>&1
        }

        format_uptime() {
          local total=$1
          local days hours mins
          days=$((total / 86400))
          hours=$(((total % 86400) / 3600))
          mins=$(((total % 3600) / 60))

          if [ "$days" -gt 0 ]; then
            printf '%sd %sh' "$days" "$hours"
          elif [ "$hours" -gt 0 ]; then
            printf '%sh %sm' "$hours" "$mins"
          else
            printf '%sm' "$mins"
          fi
        }

        fetch_ip() {
          local now cached_ts ip
          now=$(${pkgs.coreutils}/bin/date +%s)
          ${pkgs.coreutils}/bin/mkdir -p "$CACHE_DIR"

          if [ -f "$IP_FILE" ] && [ -f "$TS_FILE" ]; then
            cached_ts=$(${pkgs.coreutils}/bin/cat "$TS_FILE" 2>/dev/null || true)
            if [ -n "$cached_ts" ] && [ $((now - cached_ts)) -lt "$REFRESH_SECS" ]; then
              ${pkgs.coreutils}/bin/cat "$IP_FILE"
              return 0
            fi
          fi

          if ip=$(${pkgs.curl}/bin/curl -fsS --max-time 3 https://icanhazip.com 2>/dev/null | ${pkgs.coreutils}/bin/tr -d '\n'); then
            printf '%s' "$ip" > "$IP_FILE"
            printf '%s' "$now" > "$TS_FILE"
            printf '%s\n' "$ip"
            return 0
          fi

          if [ -f "$IP_FILE" ]; then
            ${pkgs.coreutils}/bin/cat "$IP_FILE"
            return 0
          fi

          return 1
        }

        if [ "''${1:-}" = "toggle" ]; then
          if ! service_exists; then
            exit 0
          fi

          case "$(${pkgs.systemd}/bin/systemctl is-active "$SERVICE" 2>/dev/null || true)" in
            active)
              exec ${pkgs.sudo}/bin/sudo ${toggleScript}/bin/vless-toggle down
              ;;
            *)
              exec ${pkgs.sudo}/bin/sudo ${toggleScript}/bin/vless-toggle up
              ;;
          esac
        fi

        if ! service_exists; then
          print_json "󱚡" "inactive" "VLESS: Inactive"
          exit 0
        fi

        status="$(${pkgs.systemd}/bin/systemctl is-active "$SERVICE" 2>/dev/null || true)"
        case "$status" in
          active)
            now=$(${pkgs.coreutils}/bin/date +%s)
            started_at="$(${pkgs.systemd}/bin/systemctl show -p ActiveEnterTimestamp --value "$SERVICE" 2>/dev/null || true)"
            uptime="unknown"
            if [ -n "$started_at" ]; then
              started_epoch=$(${pkgs.coreutils}/bin/date -d "$started_at" +%s 2>/dev/null || true)
              if [ -n "$started_epoch" ]; then
                uptime=$(format_uptime $((now - started_epoch)))
              fi
            fi

            ip="unavailable"
            if fetched_ip=$(fetch_ip); then
              ip=$fetched_ip
            fi

            print_json "󰖂" "active" "VLESS: Active
    IP: $ip
    Uptime: $uptime"
            ;;
          failed)
            print_json "󰖂" "failed" "VLESS: Failed"
            ;;
          *)
            print_json "󱚡" "inactive" "VLESS: Inactive"
            ;;
        esac
  '';
  restoreIpv6RaScript = pkgs.writeShellScript "restore-${serviceName}-ipv6-ra" ''
    set -euo pipefail

    # sing-box TUN auto-routing can leave IPv6 router advertisements disabled
    # on physical uplinks, which breaks LAN IPv6 even when kernel IPv6 is on.
    for ifacePath in /sys/class/net/*; do
      iface="''${ifacePath##*/}"
      if [[ ! -e "$ifacePath/device" ]]; then
        continue
      fi

      raPath="/proc/sys/net/ipv6/conf/$iface/accept_ra"
      if [[ -w "$raPath" ]]; then
        printf '2\n' > "$raPath"
      fi
    done
  '';
  prepareConfigCommands =
    if cfg.configUser == null then
      [
        "${pkgs.coreutils}/bin/install -Dm0400 ${lib.escapeShellArg cfg.configPath} ${lib.escapeShellArg runtimeConfig}"
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
      description = "Absolute path to the sing-box JSON configuration on disk. The file is exposed to the service under /run/${serviceName}/config.json.";
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
      description = "User that can read the sing-box configuration file when the service itself cannot (for example, if the file lives on a FUSE mount without allow_other). When set, the configuration is staged using this user before the service starts.";
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
      toggleScript
      waybarScript
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
            sudo ${toggleScript}/bin/vless-toggle up
            ;;
          down)
            sudo ${toggleScript}/bin/vless-toggle down
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

    security.sudo.extraRules = [
      {
        groups = [ "wheel" ];
        commands = [
          {
            command = "${toggleScript}/bin/vless-toggle";
            options = [ "NOPASSWD" ];
          }
        ];
      }
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
        ExecStart = "${cfg.package}/bin/sing-box run --disable-color -c ${lib.escapeShellArg runtimeConfig}";
        ExecStartPre = prepareConfigCommands;
        ExecStartPost = restoreIpv6RaScript;
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

    # Allow Docker bridge traffic to reach the sing-box redirect port so
    # containers can use the tunnel.
    networking.firewall.extraInputRules = lib.mkIf config.virtualisation.docker.enable ''
      -i docker0 -p tcp --dport 41935 -j ACCEPT
      -i br-+ -p tcp --dport 41935 -j ACCEPT
    '';
  };
}
