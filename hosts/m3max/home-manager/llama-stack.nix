{
  config,
  lib,
  pkgs,
  ...
}:
let
  homeDirectory = config.home.homeDirectory;
  generationLabel = "ai.llama.server";
  dashboardLabel = "ai.llama.dashboard";
  generationLogPath = "${homeDirectory}/Library/Logs/llama-server.log";
  dashboardLogPath = "${homeDirectory}/Library/Logs/llama-dashboard.log";
  dashboardDirectory = "${homeDirectory}/pro/llama-dashboard";
  dashboardDbPath = "${homeDirectory}/Library/Application Support/llama-dashboard/llama-dashboard.db";

  mkLlamaPlist =
    {
      label,
      logPath,
      arguments,
    }:
    pkgs.writeText "${label}.plist" (
      lib.generators.toPlist { escape = true; } {
        Label = label;
        KeepAlive = true;
        ProcessType = "Background";
        ProgramArguments = [ "/opt/homebrew/bin/llama-server" ] ++ arguments;
        RunAtLoad = true;
        StandardErrorPath = logPath;
        StandardOutPath = logPath;
        ThrottleInterval = 10;
        WorkingDirectory = homeDirectory;
        EnvironmentVariables = {
          HOME = homeDirectory;
          PATH = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin";
        };
      }
    );

  generationPlist = mkLlamaPlist {
    label = generationLabel;
    logPath = generationLogPath;
    arguments = [
      "-hf"
      "unsloth/Qwen3.6-35B-A3B-MTP-GGUF:UD-Q4_K_M"
      "--host"
      "0.0.0.0"
      "--port"
      "8080"
      "-c"
      "16384"
      "--parallel"
      "1"
      "--flash-attn"
      "on"
      "--spec-type"
      "draft-mtp"
      "--spec-draft-n-max"
      "2"
      "--cache-ram"
      "1024"
      "--n-gpu-layers"
      "all"
      "--metrics"
      "--reasoning"
      "off"
      "--chat-template-kwargs"
      ''{"enable_thinking": false}''
    ];
  };

  dashboardPlist = pkgs.writeText "${dashboardLabel}.plist" (
    lib.generators.toPlist { escape = true; } {
      Label = dashboardLabel;
      KeepAlive = true;
      ProcessType = "Background";
      ProgramArguments = [
        "${pkgs.nodejs_24}/bin/npm"
        "start"
      ];
      RunAtLoad = true;
      StandardErrorPath = dashboardLogPath;
      StandardOutPath = dashboardLogPath;
      ThrottleInterval = 10;
      WorkingDirectory = dashboardDirectory;
      EnvironmentVariables = {
        HOME = homeDirectory;
        PATH = "${pkgs.nodejs_24}/bin:/usr/bin:/bin";
        NODE_ENV = "production";
        LLD_UPSTREAMS_JSON = builtins.toJSON [
          {
            key = "generation";
            label = "Generation";
            role = "generation";
            upstreamUrl = "http://127.0.0.1:8080";
            listener = {
              host = "0.0.0.0";
              port = 8081;
            };
          }
        ];
        LLD_DEFAULT_UPSTREAM_KEY = "generation";
        LLD_UI_PORT = "8082";
        LLD_HOST = "0.0.0.0";
        LLD_DB_PATH = dashboardDbPath;
      };
    }
  );

  llamaStack = pkgs.writeShellApplication {
    name = "llama-stack";
    runtimeInputs = with pkgs; [
      coreutils
      curl
      gawk
      nodejs_24
    ];
    text = ''
      set -euo pipefail

      domain="gui/$(id -u)"
      generation_label=${lib.escapeShellArg generationLabel}
      generation_plist=${lib.escapeShellArg (toString generationPlist)}
      generation_log=${lib.escapeShellArg generationLogPath}
      dashboard_label=${lib.escapeShellArg dashboardLabel}
      dashboard_plist=${lib.escapeShellArg (toString dashboardPlist)}
      dashboard_log=${lib.escapeShellArg dashboardLogPath}
      dashboard_dir=${lib.escapeShellArg dashboardDirectory}
      dashboard_db=${lib.escapeShellArg dashboardDbPath}

      # The loaded Q4 Metal model uses about 24 GiB at this context size.
      # Keep at least 8 GiB for macOS and reject hosts with less than 32 GiB.
      required_total_mib=32768
      estimated_stack_mib=24576
      minimum_free_percent=65

      usage() {
        cat <<'EOF'
      Usage: llama-stack {preflight|start|stop|restart|status|logs [-f]}

        preflight  Verify RAM and disk capacity for the native Metal model
        start      Start the native Metal server and the dashboard
        stop       Stop the dashboard and llama-server process
        restart    Restart the full stack
        status     Show launchd and API status
        logs       Show recent server and dashboard logs
        logs -f    Follow server and dashboard logs
      EOF
      }

      current_free_percent() {
        /usr/bin/memory_pressure -Q |
          awk '/System-wide memory free percentage:/ { gsub(/%/, "", $5); print $5 }'
      }

      preflight() {
        local total_bytes total_mib free_percent available_disk_kib available_disk_mib

        total_bytes=$(/usr/sbin/sysctl -n hw.memsize)
        total_mib=$((total_bytes / 1024 / 1024))
        free_percent=$(current_free_percent)
        if ((free_percent < minimum_free_percent)); then
          printf 'Waiting for macOS to release memory'
          for _ in $(seq 1 30); do
            sleep 1
            free_percent=$(current_free_percent)
            if ((free_percent >= minimum_free_percent)); then
              break
            fi
            printf '.'
          done
          printf '\n'
        fi
        available_disk_kib=$(/bin/df -Pk "$HOME" | awk 'NR == 2 { print $4 }')
        available_disk_mib=$((available_disk_kib / 1024))

        printf 'RAM: %s MiB total; %s%% currently available\n' "$total_mib" "$free_percent"
        printf 'Estimated peak for the model: %s MiB; required host RAM: %s MiB\n' \
          "$estimated_stack_mib" "$required_total_mib"
        printf 'Disk available for model cache: %s MiB\n' "$available_disk_mib"

        if ((total_mib < required_total_mib)); then
          printf 'llama-stack: the model needs a Mac with at least %s MiB RAM\n' \
            "$required_total_mib" >&2
          return 1
        fi
        if ((free_percent < minimum_free_percent)); then
          printf 'llama-stack: only %s%% memory is currently available; close memory-heavy apps first\n' \
            "$free_percent" >&2
          return 1
        fi
        if ((available_disk_mib < 28672)); then
          printf 'llama-stack: at least 28672 MiB free disk space is needed for the model cache\n' >&2
          return 1
        fi

        printf 'Preflight passed\n'
      }

      service_loaded() {
        local label=$1
        /bin/launchctl print "$domain/$label" >/dev/null 2>&1
      }

      service_healthy() {
        local port=$1
        curl --fail --silent --max-time 2 "http://127.0.0.1:$port/health" >/dev/null
      }

      start_service() {
        local name=$1 label=$2 plist=$3

        if service_loaded "$label"; then
          printf '%s is already started\n' "$name"
          return
        fi

        if ! /bin/launchctl bootstrap "$domain" "$plist"; then
          printf 'llama-stack: failed to start %s\n' "$name" >&2
          return 1
        fi
        printf '%s started\n' "$name"
      }

      stop_service() {
        local name=$1 label=$2

        if ! service_loaded "$label"; then
          printf '%s is already stopped\n' "$name"
          return
        fi

        if ! /bin/launchctl bootout "$domain/$label"; then
          printf 'llama-stack: failed to stop %s\n' "$name" >&2
          return 1
        fi
        printf '%s stopped\n' "$name"
      }

      start_servers() {
        start_service llama-server "$generation_label" "$generation_plist"
      }

      stop_servers() {
        local failed=0

        stop_service llama-server "$generation_label" || failed=1
        return "$failed"
      }

      prepare_dashboard() {
        local lock_hash installed_hash stamp_file

        if [[ ! -f "$dashboard_dir/package.json" ]]; then
          printf 'llama-stack: dashboard checkout not found: %s\n' "$dashboard_dir" >&2
          return 1
        fi
        if [[ ! -f "$dashboard_dir/package-lock.json" ]]; then
          printf 'llama-stack: dashboard lockfile not found: %s/package-lock.json\n' \
            "$dashboard_dir" >&2
          return 1
        fi

        mkdir -p "$(dirname "$dashboard_db")"
        stamp_file="$dashboard_dir/node_modules/.llama-stack-lock-sha256"
        lock_hash=$(/usr/bin/shasum -a 256 "$dashboard_dir/package-lock.json" | awk '{ print $1 }')
        installed_hash=$(cat "$stamp_file" 2>/dev/null || true)
        if [[ ! -x "$dashboard_dir/node_modules/.bin/tsx" || "$installed_hash" != "$lock_hash" ]]; then
          printf 'Installing dashboard dependencies\n'
          (cd "$dashboard_dir" && npm ci)
          printf '%s\n' "$lock_hash" > "$stamp_file"
        fi

        printf 'Building llama-dashboard\n'
        (cd "$dashboard_dir" && npm run build)
      }

      start_stack() {
        preflight
        prepare_dashboard
        start_servers

        if ! start_service llama-dashboard "$dashboard_label" "$dashboard_plist"; then
          printf 'llama-stack: dashboard failed to start; stopping native servers\n' >&2
          stop_servers || true
          return 1
        fi

        printf 'Dashboard: http://localhost:8082\n'
        printf 'Generation proxy: http://localhost:8081\n'
      }

      stop_stack() {
        local failed=0

        stop_service llama-dashboard "$dashboard_label" || failed=1
        stop_servers || failed=1

        return "$failed"
      }

      print_service_status() {
        local name=$1 label=$2 port=$3

        if service_loaded "$label"; then
          printf '%s: loaded' "$name"
          if service_healthy "$port"; then
            printf ' (healthy)\n'
          else
            printf ' (downloading, loading, or unhealthy)\n'
          fi
        else
          printf '%s: stopped\n' "$name"
        fi
      }

      status_stack() {
        print_service_status llama-server "$generation_label" 8080
        print_service_status llama-dashboard "$dashboard_label" 8082
      }

      show_file_log() {
        local title=$1 log_file=$2

        printf '== %s ==\n' "$title"
        if [[ -f "$log_file" ]]; then
          tail -n 100 "$log_file"
        else
          printf 'No log yet: %s\n' "$log_file"
        fi
      }

      show_logs() {
        local follow="''${1:-}"

        show_file_log llama-server "$generation_log"
        printf '\n'
        show_file_log llama-dashboard "$dashboard_log"

        if [[ "$follow" == "-f" ]]; then
          mkdir -p "$(dirname "$generation_log")"
          touch "$generation_log" "$dashboard_log"
          tail -n 0 -F "$generation_log" "$dashboard_log"
        fi
      }

      case "''${1:-}" in
        preflight)
          [[ $# -eq 1 ]] || { usage >&2; exit 2; }
          preflight
          ;;
        start)
          [[ $# -eq 1 ]] || { usage >&2; exit 2; }
          start_stack
          ;;
        stop)
          [[ $# -eq 1 ]] || { usage >&2; exit 2; }
          stop_stack
          ;;
        restart)
          [[ $# -eq 1 ]] || { usage >&2; exit 2; }
          stop_stack
          start_stack
          ;;
        status)
          [[ $# -eq 1 ]] || { usage >&2; exit 2; }
          status_stack
          ;;
        logs)
          [[ $# -le 2 ]] || { usage >&2; exit 2; }
          if [[ $# -eq 2 && "$2" != "-f" ]]; then
            usage >&2
            exit 2
          fi
          show_logs "''${2:-}"
          ;;
        -h|--help|help|"")
          usage
          ;;
        *)
          usage >&2
          exit 2
          ;;
      esac
    '';
  };
in
{
  home.packages = [ llamaStack ];
}
