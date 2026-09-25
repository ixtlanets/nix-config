{ pkgs, ... }:

let
  socket = "/var/run/tailscaled-cli.sock";
  state = "/var/db/tailscaled-cli.state";
  zenbookIp = "100.114.155.30";

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
      target=${zenbookIp}
      route_info=$(/sbin/route -n get "$target" 2>/dev/null || true)
      destination=$(printf '%s\n' "$route_info" | /usr/bin/awk '$1 == "destination:" { print $2; exit }')
      current_interface=$(printf '%s\n' "$route_info" | /usr/bin/awk '$1 == "interface:" { print $2; exit }')

      backend=$(tailscale-cli status --json --peers=false 2>/dev/null | jq -r '.BackendState // empty' || true)
      if [ "$backend" != Running ]; then
        if [ "$destination" = "$target" ] && [[ "$current_interface" == utun* ]]; then
          /sbin/route -n delete -host "$target"
        fi
        exit 0
      fi

      own_ip=$(tailscale-cli ip -4 | /usr/bin/head -n 1)
      [ -n "$own_ip" ] || exit 1
      own_route=$(/sbin/route -n get "$own_ip")
      tailscale_interface=$(printf '%s\n' "$own_route" | /usr/bin/awk '$1 == "interface:" { print $2; exit }')
      [[ "$tailscale_interface" == utun* ]] || exit 1

      if [ "$destination" = "$target" ] && [ "$current_interface" = "$tailscale_interface" ]; then
        exit 0
      fi

      if [ "$destination" = "$target" ]; then
        /sbin/route -n delete -host "$target"
      fi
      /sbin/route -n add -host "$target" -interface "$tailscale_interface"
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
