{
  config,
  lib,
  pkgs,
  ...
}:
let
  homeDirectory = config.home.homeDirectory;
  label = "ai.llama.server";
  logPath = "${homeDirectory}/Library/Logs/llama-server.log";
  composeFile = ../docker/llama-server/docker-compose.yml;

  llamaServerPlist = pkgs.writeText "${label}.plist" (
    lib.generators.toPlist { escape = true; } {
      Label = label;
      KeepAlive = true;
      ProcessType = "Background";
      ProgramArguments = [
        "/opt/homebrew/bin/llama-server"
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

  llamaStack = pkgs.writeShellApplication {
    name = "llama-stack";
    runtimeInputs = with pkgs; [
      coreutils
      curl
    ];
    text = ''
      set -euo pipefail

      label=${lib.escapeShellArg label}
      domain="gui/$(id -u)"
      service="$domain/$label"
      plist=${lib.escapeShellArg (toString llamaServerPlist)}
      compose_file=${lib.escapeShellArg (toString composeFile)}
      log_file=${lib.escapeShellArg logPath}
      docker_bin=""

      usage() {
        cat <<'EOF'
      Usage: llama-stack {start|stop|restart|status|logs [-f]}

        start    Start dashboard and native Metal llama-server
        stop     Stop dashboard and llama-server
        restart  Restart the full stack
        status   Show launchd, API, and Compose status
        logs     Show recent server and dashboard logs
        logs -f  Follow server and dashboard logs
      EOF
      }

      find_docker() {
        if command -v docker >/dev/null 2>&1; then
          docker_bin=$(command -v docker)
        elif [[ -x /usr/local/bin/docker ]]; then
          docker_bin=/usr/local/bin/docker
        else
          return 1
        fi
      }

      docker_ready() {
        [[ -n "$docker_bin" ]] && "$docker_bin" info >/dev/null 2>&1
      }

      ensure_docker() {
        if ! find_docker; then
          printf 'llama-stack: Docker CLI not found\n' >&2
          return 1
        fi

        if docker_ready; then
          return
        fi

        printf 'Starting Docker Desktop'
        /usr/bin/open -a Docker
        for _ in $(seq 1 120); do
          if docker_ready; then
            printf '\nDocker Desktop is ready\n'
            return
          fi
          printf '.'
          sleep 1
        done

        printf '\nllama-stack: Docker Desktop did not become ready within 120 seconds\n' >&2
        return 1
      }

      compose() {
        "$docker_bin" compose -f "$compose_file" "$@"
      }

      server_loaded() {
        /bin/launchctl print "$service" >/dev/null 2>&1
      }

      start_server() {
        if server_loaded; then
          printf 'llama-server is already started\n'
          return
        fi

        if ! /bin/launchctl bootstrap "$domain" "$plist"; then
          printf 'llama-stack: failed to start llama-server\n' >&2
          return 1
        fi
        printf 'llama-server started; model may still be loading\n'
      }

      stop_server() {
        if ! server_loaded; then
          printf 'llama-server is already stopped\n'
          return
        fi

        if ! /bin/launchctl bootout "$service"; then
          printf 'llama-stack: failed to stop llama-server\n' >&2
          return 1
        fi
        printf 'llama-server stopped\n'
      }

      start_stack() {
        ensure_docker
        compose up -d --build

        if ! start_server; then
          printf 'llama-stack: llama-server failed to start; stopping dashboard\n' >&2
          compose down
          return 1
        fi

        printf 'Dashboard: http://localhost:8082\n'
        printf 'Generation proxy: http://localhost:8081\n'
      }

      stop_stack() {
        local failed=0

        if find_docker && docker_ready; then
          if ! compose down; then
            printf 'llama-stack: failed to stop dashboard\n' >&2
            failed=1
          fi
        else
          printf 'Docker Desktop is not running; dashboard is already stopped\n'
        fi
        if ! stop_server; then
          failed=1
        fi

        return "$failed"
      }

      status_stack() {
        if server_loaded; then
          printf 'llama-server: loaded'
          if curl --fail --silent --max-time 2 http://127.0.0.1:8080/health >/dev/null; then
            printf ' (healthy)\n'
          else
            printf ' (loading or unhealthy)\n'
          fi
        else
          printf 'llama-server: stopped\n'
        fi

        if find_docker && docker_ready; then
          printf '\nDashboard Compose status:\n'
          dashboard_id=$(compose ps --all --quiet)
          if [[ -n "$dashboard_id" ]]; then
            compose ps --all
          else
            printf 'llama-dashboard: stopped\n'
          fi
        else
          printf 'llama-dashboard: stopped (Docker Desktop is not running)\n'
        fi
      }

      show_logs() {
        local follow="''${1:-}"

        printf '== llama-server ==\n'
        if [[ -f "$log_file" ]]; then
          tail -n 100 "$log_file"
        else
          printf 'No llama-server log yet: %s\n' "$log_file"
        fi

        printf '\n== llama-dashboard ==\n'
        if ! find_docker || ! docker_ready; then
          printf 'Docker Desktop is not running\n'
          return
        fi

        if [[ "$follow" != "-f" ]]; then
          compose logs --tail 100
          return
        fi

        mkdir -p "$(dirname "$log_file")"
        touch "$log_file"
        tail -n 0 -F "$log_file" &
        server_log_pid=$!
        trap 'kill "$server_log_pid" 2>/dev/null || true' EXIT INT TERM
        compose logs --tail 0 -f
      }

      case "''${1:-}" in
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
