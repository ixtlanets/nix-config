{ pkgs, ... }:
{
  environment.systemPackages = with pkgs; [
    # SRC: https://github.com/FlyGoat/RyzenAdj
    # ./ryzenadj --stapm-limit=45000 --fast-limit=45000 --slow-limit=45000 --tctl-temp=90
    # ryzenAdj --info
    # radg [TEMP]
    ryzenadj

    # SRC: https://github.com/nbfc-linux/nbfc-linux
    nbfc-linux
  ];

  systemd.services.radj = {
    enable = true;
    description = "Ryzen Adj temperature limiter.";
    serviceConfig = {
      Type = "simple";
      Restart = "always";
      RestartSec = "5s";
    };
    wantedBy = [ "multi-user.target" ];
    path = with pkgs; [
      coreutils
      ryzenadj
    ];
    script = ''
      while true; do
        # Check if AC adapter is connected
        if [ "$(cat /sys/class/power_supply/AC0/online)" -eq "1" ]; then
            # On AC power
            ryzenadj --tctl-temp=80 &> /dev/null
        else
            # On battery
            ryzenadj --tctl-temp=55 &> /dev/null
        fi
        sleep 60
      done
    '';
  };
}
