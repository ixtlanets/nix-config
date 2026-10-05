{ pkgs, ... }:

let
  socket = "/var/run/tailscaled-cli.sock";
  state = "/var/db/tailscaled-cli.state";
  zenbookIp = "100.114.155.30";
  # All tailnet peers that sing-box's 100.64/10 route shadows on m3max.
  # The /etc/resolver approach handles DNS; these host routes fix reply path.
  peerIps = [
    zenbookIp
    "100.80.137.100" # t14s
    "100.95.213.117" # um790pro
    "100.107.212.33" # x1carbon
  ];

  tailscaleCli = pkgs.writeShellScriptBin "tailscale-cli" ''
    exec ${pkgs.tailscale}/bin/tailscale --socket=${socket} "$@"
  '';

  tailnetRoutes = pkgs.writeShellApplication {
    name = "m3max-tailnet-routes";
    runtimeInputs = [
      pkgs.jq
      tailscaleCli
    ];
    text = ''
      backend=$(tailscale-cli status --json --peers=false 2>/dev/null | jq -r '.BackendState // empty' || true)

      tailscale_interface=""
      if [ "$backend" = Running ]; then
        own_ip=$(tailscale-cli ip -4 | /usr/bin/head -n 1)
        if [ -n "$own_ip" ]; then
          own_route=$(/sbin/route -n get "$own_ip")
          tailscale_interface=$(printf '%s\n' "$own_route" | /usr/bin/awk '$1 == "interface:" { print $2; exit }')
        fi
      fi

      for target in ${toString peerIps}; do
        route_info=$(/sbin/route -n get "$target" 2>/dev/null || true)
        destination=$(printf '%s\n' "$route_info" | /usr/bin/awk '$1 == "destination:" { print $2; exit }')
        current_interface=$(printf '%s\n' "$route_info" | /usr/bin/awk '$1 == "interface:" { print $2; exit }')

        if [ "$backend" != Running ] || [ -z "$tailscale_interface" ] || [[ "$tailscale_interface" != utun* ]]; then
          # Daemon down: drop stale host routes so the tailnet does not blackhole.
          if [ "$destination" = "$target" ] && [[ "$current_interface" == utun* ]]; then
            /sbin/route -n delete -host "$target"
          fi
          continue
        fi

        if [ "$destination" = "$target" ] && [ "$current_interface" = "$tailscale_interface" ]; then
          continue
        fi

        if [ "$destination" = "$target" ]; then
          /sbin/route -n delete -host "$target"
        fi
        /sbin/route -n add -host "$target" -interface "$tailscale_interface"
      done
    '';
  };
in
{
  environment.systemPackages = [
    tailscaleCli
    tailnetRoutes
  ];

  # The CLI-only macOS daemon does not configure MagicDNS in the system resolver.
  # Keep sing-box's default DNS and send only the tailnet domain to Tailscale.
  environment.etc."resolver/tailf108.ts.net".text = ''
    nameserver 100.100.100.100
  '';

  # m1max has no active Tailscale node; um790pro advertises its LAN /32.
  # A hosts entry keeps the same name at home and on LTE without changing
  # sing-box's DNS configuration or publishing a private address in public DNS.
  system.activationScripts.postActivation.text = ''
    if ! /usr/bin/grep -q '[[:space:]]m1max\.nikcode\.xyz\([[:space:]]\|$\)' /etc/hosts; then
      /usr/bin/printf '\n192.168.1.174 m1max.nikcode.xyz\n' >> /etc/hosts
    fi
  '';

  launchd.daemons = {
    tailscaled-cli = {
      command = "${pkgs.tailscale}/bin/tailscaled --tun=utun --state=${state} --socket=${socket}";
      serviceConfig = {
        RunAtLoad = true;
        KeepAlive = true;
        StandardOutPath = "/var/log/tailscaled-cli.log";
        StandardErrorPath = "/var/log/tailscaled-cli.log";
      };
    };

    m3max-tailnet-routes = {
      command = "${tailnetRoutes}/bin/m3max-tailnet-routes";
      serviceConfig = {
        RunAtLoad = true;
        StartInterval = 15;
        StandardOutPath = "/var/log/m3max-tailnet-routes.log";
        StandardErrorPath = "/var/log/m3max-tailnet-routes.log";
      };
    };
  };
}
